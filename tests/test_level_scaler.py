"""Unit coverage for Climb authored 6x24 -> platform 6x33 level scaling."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from api.level_scaler import prepare_level_for_platform, scale_cells


TARGET_ROWS = 6
TARGET_COLS = 33
SOURCE_ROWS = 6
SOURCE_COLS = 24
FLOOR_LIGHT = "floor_light"


def _game(**overrides):
    values = dict(
        name="climb-test",
        row=SOURCE_ROWS,
        col=SOURCE_COLS,
        zone_row_from=0,
        zone_row_to=SOURCE_ROWS,
        zone_col_from=0,
        zone_col_to=SOURCE_COLS,
        corner_line_start=0,
        wall_light=False,
        screen=False,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _floor_group(cells, *, scale="both", speed=0, activity_area=None, **overrides):
    values = dict(
        name="g",
        type=FLOOR_LIGHT,
        start_member=set(cells),
        scale=scale,
        speed=speed,
        start_area=1,
        activity_area=activity_area
        or [(0, SOURCE_ROWS), (0, SOURCE_COLS)],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("mode", "source", "expected"),
    (
        ("both", {(0, 0)}, {(0, 0)}),
        ("both", {(0, 1)}, {(0, 1), (0, 2)}),
        ("both", {(0, 23)}, {(0, 32)}),
        ("col", {(3, 0)}, {(3, 0)}),
        ("col", {(3, 23)}, {(3, 32)}),
        ("row", {(0, 10)}, {(0, 14)}),  # rows unchanged; unscaled col recenters
        ("none", {(0, 0)}, {(0, 0)}),
        ("none", {(0, 23)}, {(0, 32)}),
        ("none2edge", {(5, 23)}, {(5, 32)}),
    ),
)
def test_scale_cells_6x24_to_6x33_modes(mode, source, expected):
    result = scale_cells(
        source,
        source_rows=SOURCE_ROWS,
        source_cols=SOURCE_COLS,
        target_rows=TARGET_ROWS,
        target_cols=TARGET_COLS,
        mode=mode,
    )
    assert result == expected


def test_prepare_scales_zone_and_partial_activity_area_with_move_range():
    game = _game()
    group = _floor_group(
        {(2, 23)},
        scale="both",
        activity_area=[(0, 6), (13, 24)],
    )
    source_snapshot = copy.deepcopy(group.start_member)

    prepared_groups, prepared_game = prepare_level_for_platform(
        {"g": group},
        game,
        target_rows=TARGET_ROWS,
        target_cols=TARGET_COLS,
        enable_wall_light=False,
        enable_screen_light=False,
    )

    assert (
        prepared_game.zone_row_from,
        prepared_game.zone_row_to,
        prepared_game.zone_col_from,
        prepared_game.zone_col_to,
    ) == (0, 6, 0, 33)
    assert (prepared_game.row, prepared_game.col) == (TARGET_ROWS, TARGET_COLS)
    assert prepared_groups["g"].activity_area == [(0, 6), (18, 33)]
    assert any(col >= 24 for _, col in prepared_groups["g"].start_member)
    assert group.start_member == source_snapshot


def test_static_no_use_cells_are_removed_moving_groups_keep_them():
    static = _floor_group({(0, 2)}, scale="both", speed=0)
    moving = _floor_group({(0, 2)}, scale="both", speed=1.0)

    prepared_groups, _ = prepare_level_for_platform(
        {"static": static, "moving": moving},
        _game(),
        target_rows=TARGET_ROWS,
        target_cols=TARGET_COLS,
        enable_wall_light=False,
        enable_screen_light=False,
        floor_layout_coors_no_use={(0, 3)},
    )

    # both-mode maps authored col 2 -> platform cols 3..4
    assert (0, 3) not in prepared_groups["static"].start_member
    assert (0, 3) in prepared_groups["moving"].start_member


def test_rejects_corner_line_layouts():
    with pytest.raises(ValueError, match="corner_line_start"):
        prepare_level_for_platform(
            {"g": _floor_group({(0, 0)})},
            _game(corner_line_start=1),
            target_rows=TARGET_ROWS,
            target_cols=TARGET_COLS,
            enable_wall_light=False,
            enable_screen_light=False,
        )


def test_enabled_wall_or_screen_groups_are_rejected():
    wall = SimpleNamespace(
        name="wall",
        type="wall_light",
        start_member=[0, 1],
        activity_area=[(0, 6), (0, 24)],
        scale="both",
        speed=0,
    )
    with pytest.raises(ValueError, match="wall_light|screen_light"):
        prepare_level_for_platform(
            {"wall": wall},
            _game(),
            target_rows=TARGET_ROWS,
            target_cols=TARGET_COLS,
            enable_wall_light=True,
            enable_screen_light=False,
        )


def test_disabled_wall_groups_are_dropped():
    wall = SimpleNamespace(
        name="wall",
        type="wall_light",
        start_member=[0, 1],
        activity_area=[(0, 6), (0, 24)],
        scale="both",
        speed=0,
    )
    floor = _floor_group({(1, 1)})
    prepared_groups, _ = prepare_level_for_platform(
        {"wall": wall, "floor": floor},
        _game(),
        target_rows=TARGET_ROWS,
        target_cols=TARGET_COLS,
        enable_wall_light=False,
        enable_screen_light=False,
    )
    assert "wall" not in prepared_groups
    assert "floor" in prepared_groups


def test_prepare_deep_copies_so_source_objects_stay_raw():
    game = _game()
    group = _floor_group({(0, 23)}, scale="both")
    prepared_groups, prepared_game = prepare_level_for_platform(
        {"g": group},
        game,
        target_rows=TARGET_ROWS,
        target_cols=TARGET_COLS,
        enable_wall_light=False,
        enable_screen_light=False,
    )
    prepared_groups["g"].start_member.add((0, 99))
    assert (0, 99) not in group.start_member
    assert game.col == SOURCE_COLS
    assert prepared_game.col == TARGET_COLS
