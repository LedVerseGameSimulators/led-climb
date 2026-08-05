"""Integration coverage for Climb level preparation at the game boundary."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from api import game_manager

ROOT = Path(__file__).resolve().parents[1]
FLOOR_LIGHT = "floor_light"
A001 = ROOT / "games" / "source" / "-" / "A001.led"


def _settings(**overrides):
    values = {
        "grid_rows": 6,
        "grid_cols": 33,
        "wall_light": False,
        "screen_light": False,
        "floor_layout_coors_no_use": [],
    }
    values.update(overrides)
    return values


def test_prepare_real_a001_expands_to_full_6x33_platform():
    groups, game = game_manager._load_level_file(A001)
    assert (game.row, game.col) == (6, 24)
    table = game_manager.HeadlessLedTable(100, 6, 33)

    prepared_groups, prepared_game = game_manager._prepare_level_attempt(
        groups,
        game,
        led_table=table,
        settings=_settings(),
        level_id="A001",
    )

    assert (prepared_game.row, prepared_game.col) == (6, 33)
    assert (
        prepared_game.zone_row_from,
        prepared_game.zone_row_to,
        prepared_game.zone_col_from,
        prepared_game.zone_col_to,
    ) == (0, 6, 0, 33)
    floor_cells = {
        tuple(cell)
        for group in prepared_groups.values()
        if getattr(group, "type", None) == FLOOR_LIGHT
        for cell in (getattr(group, "start_member", ()) or ())
    }
    assert floor_cells
    assert max(col for _, col in floor_cells) >= 24
    assert all(0 <= r < 6 and 0 <= c < 33 for r, c in floor_cells)
    assert game.col == 24  # source object unchanged


def test_run_level_attempt_orders_load_reset_prepare_setup_play():
    events = []
    dict_group = {"g": SimpleNamespace(type=FLOOR_LIGHT)}
    game_obj = SimpleNamespace(row=6, col=24)

    def loader(path):
        events.append("load")
        return dict_group, game_obj

    def prepare(groups, game, *, led_table, settings, level_id):
        events.append("prepare")
        assert groups is dict_group
        assert game is game_obj
        return groups, game

    def reset():
        events.append("reset")

    def setup(groups, game):
        events.append("setup")

    def play(groups):
        events.append("play")

    with mock.patch.object(game_manager, "_load_level_file", side_effect=loader), \
         mock.patch.object(game_manager, "_prepare_level_attempt", side_effect=prepare):
        game_manager._run_level_attempt(
            "A001.led",
            led_table=SimpleNamespace(led_row=6, led_col=33),
            settings=_settings(),
            level_id="A001",
            reset_consumer=reset,
            setup_consumer=setup,
            play_consumer=play,
        )

    assert events == ["load", "reset", "prepare", "setup", "play"]


def test_prepare_failure_never_reaches_setup_or_play():
    events = []

    def loader(path):
        events.append("load")
        return {"g": SimpleNamespace()}, SimpleNamespace(row=6, col=24)

    def prepare(*args, **kwargs):
        events.append("prepare")
        raise ValueError("boom")

    with mock.patch.object(game_manager, "_load_level_file", side_effect=loader), \
         mock.patch.object(game_manager, "_prepare_level_attempt", side_effect=prepare):
        with pytest.raises(game_manager.LevelAttemptPreparationError, match="boom"):
            game_manager._run_level_attempt(
                "bad.led",
                led_table=SimpleNamespace(led_row=6, led_col=33),
                settings=_settings(),
                level_id="bad",
                reset_consumer=lambda: events.append("reset"),
                setup_consumer=lambda g, o: events.append("setup"),
                play_consumer=lambda g: events.append("play"),
            )

    assert events == ["load", "reset", "prepare"]
    assert "setup" not in events
    assert "play" not in events


def test_load_real_settings_exposes_layout_fields_for_prepare(monkeypatch):
    game_manager._settings_cache = None

    class FakeShelf(dict):
        def close(self):
            pass

    led = FakeShelf(
        value_high="6",
        value_width="33",
        floor_layout_coors_no_use=[(0, 3), (5, 3)],
        wall_light=False,
        screen_light=False,
        corner_line_start=0,
    )
    debug = FakeShelf()

    def open_shelf(path, flag):
        return led if path == game_manager._LED_PARAM else debug

    monkeypatch.setattr(game_manager._shelve, "open", open_shelf)
    settings = game_manager.load_real_settings()
    game_manager._settings_cache = None

    assert settings["grid_rows"] == 6
    assert settings["grid_cols"] == 33
    assert settings["floor_layout_coors_no_use"] == [(0, 3), (5, 3)]
    # Onsite runtime filter stays populated from the same shelve coordinates.
    assert settings["unused_cells"] == {(0, 3), (5, 3)}
    assert settings["wall_light"] is False
    assert settings["screen_light"] is False
    assert settings["corner_line_start"] == 0


def test_fresh_reload_can_be_prepared_twice():
    table = game_manager.HeadlessLedTable(100, 6, 33)
    settings = _settings()
    first_groups, first_game = game_manager._load_level_file(A001)
    second_groups, second_game = game_manager._load_level_file(A001)

    game_manager._prepare_level_attempt(
        first_groups, first_game, led_table=table, settings=settings, level_id="A001"
    )
    prepared_groups, prepared_game = game_manager._prepare_level_attempt(
        second_groups, second_game, led_table=table, settings=settings, level_id="A001"
    )
    assert prepared_game.zone_col_to == 33
    assert prepared_groups
