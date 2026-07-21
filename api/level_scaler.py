"""Pure geometry helpers for adapting authored Climb levels to a floor platform."""

from __future__ import annotations

import copy as _copy
from decimal import Decimal as _Decimal
from decimal import ROUND_HALF_UP as _ROUND_HALF_UP
from numbers import Integral as _Integral
from typing import Any as _Any
from typing import Iterable as _Iterable
from typing import Mapping as _Mapping

__all__ = ("scale_cells", "scale_range", "prepare_level_for_platform")

_FLOOR_LIGHT = "floor_light"
_WALL_LIGHT = "wall_light"
_SCREEN_LIGHT = "screen_light"
_GROUP_TYPES = frozenset((_FLOOR_LIGHT, _WALL_LIGHT, _SCREEN_LIGHT))
_MODES = frozenset(("both", "row", "col", "none", "none2edge"))


def _integer(value, label):
    if isinstance(value, bool) or not isinstance(value, _Integral):
        raise ValueError(f"{label} must be an integer, got {value!r}")
    return int(value)


def _dimension(value, label):
    value = _integer(value, label)
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero, got {value}")
    return value


def _half_up(value):
    if isinstance(value, _Decimal):
        return int(value.quantize(_Decimal("1"), rounding=_ROUND_HALF_UP))
    return int(_Decimal(value).quantize(_Decimal("0"), rounding=_ROUND_HALF_UP))


def _scaled_boundary(value, source_size, target_size):
    return _half_up(
        _Decimal(value) * _Decimal(target_size) / _Decimal(source_size)
    )


def scale_range(
    start: int,
    stop: int,
    *,
    source_size: int,
    target_size: int,
) -> tuple[int, int]:
    """Scale a half-open integer range using Decimal ``ROUND_HALF_UP``."""
    source_size = _dimension(source_size, "source_size")
    target_size = _dimension(target_size, "target_size")
    start = _integer(start, "range start")
    stop = _integer(stop, "range stop")
    if start > stop:
        raise ValueError(
            f"range start must not exceed range stop, got ({start}, {stop})"
        )
    scaled_start = _scaled_boundary(start, source_size, target_size)
    scaled_stop = _scaled_boundary(stop, source_size, target_size)
    if start < stop and scaled_start == scaled_stop:
        if 0 <= start and stop <= source_size:
            mapped_cell = min(max(scaled_start, 0), target_size - 1)
            return mapped_cell, mapped_cell + 1
        return scaled_start, scaled_start + 1
    return scaled_start, scaled_stop


def _fixed_cell_bounds(index, indexes, source_size, target_size):
    if 0 in indexes:
        start = _Decimal(index)
    elif source_size - 1 in indexes:
        start = _Decimal(target_size - (source_size - index))
    else:
        center = (_Decimal(min(indexes)) + _Decimal(max(indexes))) / 2
        scaled_center = center * _Decimal(target_size) / _Decimal(source_size)
        start = _Decimal(index) - center + scaled_center
    return _half_up(start), _half_up(start + 1)


def _scaled_cell_bounds(index, source_size, target_size):
    start = _scaled_boundary(index, source_size, target_size)
    stop = _scaled_boundary(index + 1, source_size, target_size)
    if stop == start:
        stop = start + 1
    return start, stop


def _bound_cell(start, stop, target_size):
    """Keep even collapsed downscales on their nearest valid target cell."""
    start = min(max(start, 0), target_size - 1)
    stop = min(max(stop, start + 1), target_size)
    return start, stop


def scale_cells(
    cells: _Iterable[tuple[int, int]] | None,
    *,
    source_rows: int,
    source_cols: int,
    target_rows: int,
    target_cols: int,
    mode: str,
) -> set[tuple[int, int]]:
    """Scale floor cells according to the legacy row/column scale modes."""
    source_rows = _dimension(source_rows, "source_rows")
    source_cols = _dimension(source_cols, "source_cols")
    target_rows = _dimension(target_rows, "target_rows")
    target_cols = _dimension(target_cols, "target_cols")
    if not isinstance(mode, str) or mode not in _MODES:
        raise ValueError(
            f"scale_cells mode must be one of {sorted(_MODES)}, got {mode!r}"
        )

    source_cells = set()
    if cells is None:
        cells = ()
    try:
        members = list(cells)
    except TypeError as exc:
        raise ValueError("scale_cells members must be an iterable of (row, col)") from exc
    for member_index, member in enumerate(members):
        if not isinstance(member, (tuple, list)) or len(member) != 2:
            raise ValueError(
                f"scale_cells member {member_index} must be a (row, col) pair, "
                f"got {member!r}"
            )
        row = _integer(member[0], f"scale_cells member {member_index} row")
        col = _integer(member[1], f"scale_cells member {member_index} col")
        if not (0 <= row < source_rows and 0 <= col < source_cols):
            raise ValueError(
                f"scale_cells member {member_index} ({row}, {col}) is outside "
                f"source bounds {source_rows}x{source_cols}"
            )
        source_cells.add((row, col))

    if not source_cells:
        return set()

    normalized_mode = "none" if mode == "none2edge" else mode
    source_row_indexes = {row for row, _ in source_cells}
    source_col_indexes = {col for _, col in source_cells}
    scale_rows = normalized_mode in ("both", "row")
    scale_cols = normalized_mode in ("both", "col")
    result = set()

    for row, col in source_cells:
        if scale_rows:
            row_start, row_stop = _scaled_cell_bounds(
                row, source_rows, target_rows
            )
        else:
            row_start, row_stop = _fixed_cell_bounds(
                row, source_row_indexes, source_rows, target_rows
            )
        if scale_cols:
            col_start, col_stop = _scaled_cell_bounds(
                col, source_cols, target_cols
            )
        else:
            col_start, col_stop = _fixed_cell_bounds(
                col, source_col_indexes, source_cols, target_cols
            )

        row_start, row_stop = _bound_cell(row_start, row_stop, target_rows)
        col_start, col_stop = _bound_cell(col_start, col_stop, target_cols)
        result.update(
            (new_row, new_col)
            for new_row in range(row_start, row_stop)
            for new_col in range(col_start, col_stop)
        )

    for row, col in result:
        if not (0 <= row < target_rows and 0 <= col < target_cols):
            raise ValueError(
                f"scale_cells produced out-of-bounds cell ({row}, {col}) for "
                f"target {target_rows}x{target_cols}"
            )
    return result


def _move_range_zone_in_out(move_range, area_before, area_after):
    """Legacy activity-area scaling (center + half-extent)."""
    row_before, col_before = area_before
    row_after, col_after = area_after
    multiple_row = row_after / row_before
    multiple_col = col_after / col_before
    zone_middle_row = (move_range[0][0] + move_range[0][1]) / 2
    zone_middle_col = (move_range[1][0] + move_range[1][1]) / 2
    zone_edge_row = (move_range[0][1] - move_range[0][0]) / 2
    zone_edge_col = (move_range[1][1] - move_range[1][0]) / 2
    row_start = _half_up((zone_middle_row - zone_edge_row) * multiple_row)
    row_stop = _half_up((zone_middle_row + zone_edge_row) * multiple_row)
    col_start = _half_up((zone_middle_col - zone_edge_col) * multiple_col)
    col_stop = _half_up((zone_middle_col + zone_edge_col) * multiple_col)
    if row_start == row_stop:
        if row_start < row_after:
            row_stop = row_start + 1
        elif row_start > 0:
            row_start = row_stop - 1
    if col_start == col_stop:
        if col_start < col_after:
            col_stop = col_start + 1
        elif col_start > 0:
            col_start = col_stop - 1
    return [(row_start, row_stop), (col_start, col_stop)]


def _level_context(game):
    name = getattr(game, "name", None)
    return f"level {name!r}" if name is not None else "level"


def _validate_activity_area(area, *, group_name):
    if not isinstance(area, (tuple, list)) or len(area) != 2:
        raise ValueError(
            f"group {group_name!r} activity_area must contain row and column ranges"
        )
    ranges = []
    for axis, bounds in zip(("row", "col"), area):
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            raise ValueError(
                f"group {group_name!r} activity_area {axis} range must be "
                f"a (start, stop) pair, got {bounds!r}"
            )
        start = _integer(
            bounds[0], f"group {group_name!r} activity_area {axis} start"
        )
        stop = _integer(
            bounds[1], f"group {group_name!r} activity_area {axis} stop"
        )
        if start >= stop:
            raise ValueError(
                f"group {group_name!r} activity_area {axis} range must be "
                f"non-empty and ordered, got ({start}, {stop})"
            )
        ranges.append((start, stop))
    return ranges


def _coordinate(value, rows, cols, label):
    if (
        not isinstance(value, (tuple, list))
        or len(value) != 2
    ):
        raise ValueError(f"{label} must be an integer (row, col) pair")
    cell = (
        _integer(value[0], f"{label} row"),
        _integer(value[1], f"{label} col"),
    )
    if not (0 <= cell[0] < rows and 0 <= cell[1] < cols):
        raise ValueError(f"{label} {cell!r} is outside the {rows}x{cols} layout")
    return cell


def _group_speed(group):
    speed = getattr(group, "speed", 0)
    try:
        return float(speed)
    except (TypeError, ValueError):
        return 0.0


def prepare_level_for_platform(
    groups: _Mapping[_Any, _Any],
    game: _Any,
    *,
    target_rows: int,
    target_cols: int,
    enable_wall_light: bool = True,
    enable_screen_light: bool = True,
    floor_layout_coors_no_use=(),
) -> tuple[dict[_Any, _Any], _Any]:
    """Copy, validate, filter, and scale an authored level for one platform."""
    target_rows = _dimension(target_rows, "target_rows")
    target_cols = _dimension(target_cols, "target_cols")
    if not isinstance(enable_wall_light, bool):
        raise ValueError("enable_wall_light must be a boolean")
    if not isinstance(enable_screen_light, bool):
        raise ValueError("enable_screen_light must be a boolean")
    if not hasattr(groups, "items"):
        raise ValueError(f"{_level_context(game)} groups must be a mapping")

    context = _level_context(game)
    corner = getattr(game, "corner_line_start", 0)
    try:
        corner = int(corner or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} corner_line_start is invalid: {corner!r}") from exc
    if corner != 0:
        raise ValueError(
            f"{context} corner_line_start={corner} layouts are not supported"
        )

    try:
        source_rows = _dimension(getattr(game, "row"), f"{context} row")
        source_cols = _dimension(getattr(game, "col"), f"{context} col")
    except AttributeError as exc:
        raise ValueError(f"{context} must define row and col dimensions") from exc

    zone_values = []
    for axis, limit in (("row", source_rows), ("col", source_cols)):
        try:
            start = _integer(
                getattr(game, f"zone_{axis}_from"), f"{context} zone {axis} start"
            )
            stop = _integer(
                getattr(game, f"zone_{axis}_to"), f"{context} zone {axis} stop"
            )
        except AttributeError as exc:
            raise ValueError(f"{context} must define zone {axis} bounds") from exc
        if not (0 <= start <= stop <= limit):
            raise ValueError(
                f"{context} zone {axis} range ({start}, {stop}) is outside "
                f"authored bounds 0..{limit}"
            )
        zone_values.append((start, stop))

    no_use = {
        _coordinate(cell, target_rows, target_cols, "no-use coordinate")
        for cell in (floor_layout_coors_no_use or ())
    }

    try:
        prepared_game = _copy.deepcopy(game)
    except Exception as exc:
        raise ValueError(f"{context} deepcopy failed: {exc}") from exc

    prepared_groups = {}
    for key, original_group in groups.items():
        group_name = getattr(original_group, "name", key)
        group_type = getattr(original_group, "type", None)
        if not isinstance(group_type, str) or group_type not in _GROUP_TYPES:
            raise ValueError(
                f"{context}, group {group_name!r}: type must be one of "
                f"{sorted(_GROUP_TYPES)}, got {group_type!r}"
            )
        if group_type == _WALL_LIGHT and not enable_wall_light:
            continue
        if group_type == _SCREEN_LIGHT and not enable_screen_light:
            continue
        if group_type in (_WALL_LIGHT, _SCREEN_LIGHT):
            raise ValueError(
                f"{context}, group {group_name!r}: enabled {group_type} "
                f"groups are not supported by Climb headless scaling"
            )

        try:
            group = _copy.deepcopy(original_group)
        except Exception as exc:
            raise ValueError(
                f"{context}, group {group_name!r} deepcopy failed: {exc}"
            ) from exc
        try:
            if hasattr(group, "activity_area"):
                row_range, col_range = _validate_activity_area(
                    group.activity_area, group_name=group_name
                )
                group.activity_area = _move_range_zone_in_out(
                    [row_range, col_range],
                    (source_rows, source_cols),
                    (target_rows, target_cols),
                )

            if group_type == _FLOOR_LIGHT:
                scaled = scale_cells(
                    getattr(group, "start_member", None),
                    source_rows=source_rows,
                    source_cols=source_cols,
                    target_rows=target_rows,
                    target_cols=target_cols,
                    mode=getattr(group, "scale", None),
                )
                if _group_speed(group) == 0.0 and no_use:
                    scaled.difference_update(no_use)
                group.start_member = scaled
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{context}, group {group_name!r}: {exc}") from exc
        prepared_groups[key] = group

    prepared_game.zone_row_from, prepared_game.zone_row_to = scale_range(
        *zone_values[0], source_size=source_rows, target_size=target_rows
    )
    prepared_game.zone_col_from, prepared_game.zone_col_to = scale_range(
        *zone_values[1], source_size=source_cols, target_size=target_cols
    )
    prepared_game.row = target_rows
    prepared_game.col = target_cols
    prepared_game.wall_light = enable_wall_light
    prepared_game.screen = enable_screen_light
    prepared_game.corner_line_start = 0
    return prepared_groups, prepared_game
