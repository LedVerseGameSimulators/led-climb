# Climb level scaling (authored → wall)

Headless Climb must **upscale** every level from its authored size onto the
physical / simulator floor before `Play.running` starts. Without this step,
levels light only part of the wall and leave a blank panel on the right.

## The mismatch

| Source | Size | Notes |
|--------|------|--------|
| Authored `.led` / `.ledb` archives | **6 × 24** | All 65 shipped Climb levels |
| Venue platform (`led_parameter`) | **6 × 33** | `value_high=6`, `value_width=33` |

Rows already match. Columns need a **24 → 33** expand (factor ≈ 1.375). That
is exactly one 9-column panel of blank LEDs if scaling is skipped.

## Original game behavior

The decompiled GUI path scaled levels after shelve load via
`GameRunning.group_size_scale` in `games/game_play/game_running.py`:

1. Transform each group’s `activity_area` with `move_range_zone_in_out`
   (center + half-extent).
2. Expand floor `start_member` cells with `zone_in_out`, honoring
   `group.scale` (`both` / `row` / `col` / `none`).
3. Scale `game.zone_row_*` / `game.zone_col_*` to the platform.
4. Strip `floor_layout_coors_no_use` from **static** groups (`speed == 0`).

Idle / attract loops called this explicitly after loading the shelve. The
editor play path did the same through `read_game_and_group` (documented;
body missing from the decompile).

## Headless fix

| Piece | Role |
|-------|------|
| [`api/level_scaler.py`](../api/level_scaler.py) | Pure prepare: deep-copy + scale |
| [`api/game_manager.py`](../api/game_manager.py) | Calls prepare on **every** level attempt |

Pipeline for each marathon / life-restart attempt:

```text
_load_level_file  →  reset_for_level  →  prepare_level_for_platform
                  →  _setup_level  →  Play.running
```

Never fall back to raw authored coordinates if prepare fails: the level is
skipped and logged.

### What gets scaled

- **Floor cells** (`start_member`) — Grid-style `scale_cells` with Decimal
  `ROUND_HALF_UP`, modes `both`, `row`, `col`, `none`, `none2edge`.
- **Activity areas** — legacy `move_range_zone_in_out` (matches Climb source
  motion bounds better than simple range multiply).
- **Play zone** — `zone_*` fields; after prepare a full-board level is
  typically `(0, 6, 0, 33)`.
- **Game size** — `game.row` / `game.col` set to the platform size.

Preparation **deep-copies** the board. Reloading the archive for the next
attempt always starts from raw 6×24 again (no cumulative double-scale).

### `floor_layout_coors_no_use`

After floor scaling, cells listed in the shelve as unused are removed from
**static** groups only. Climb’s current shelve marks **all of row 0 and
row 5** unused. That matches original hardware filtering; moving groups
(`speed != 0`) keep scaled edge cells.

### Unsupported layouts (fail closed)

Climb’s shipped catalog does not use these. The scaler refuses them rather
than inventing wrong geometry:

| Feature | Meaning | Catalog today |
|---------|---------|----------------|
| `corner_line_start != 0` | Split wall-strip + floor layout | Always `0` |
| Enabled `wall_light` / `screen_light` groups | 1D perimeter / screen indices | Shelve flags `False`; no such groups |

When wall/screen are **disabled**, those groups are simply dropped.

## Runtime effects (expected)

- Lit pattern spans the full **33** columns (not only 0–23).
- Input zone accepts presses on cols **24–32**.
- Scoreable / hazard cell counts can rise after col expansion — same as the
  original GUI on this wall.
- Static decoration on dead rows may disappear after `no_use` strip.

## How to verify

Unit / manager tests:

```bash
cd led-climb
python3 -m pytest tests/test_level_scaler.py tests/test_game_manager_level_scaling.py -q
```

Catalog smoke (all archives prepare to 6×33, cells in bounds):

```bash
python3 -c '
from pathlib import Path
from api.game_manager import _load_level_file, _prepare_level_attempt, HeadlessLedTable, load_real_settings
s = load_real_settings()
table = HeadlessLedTable(100, s["grid_rows"], s["grid_cols"])
for p in sorted(Path("games/source").glob("*/*.*")):
    dg, go = _load_level_file(str(p))
    pg, pgo = _prepare_level_attempt(dg, go, led_table=table, settings=s, level_id=p.stem)
    assert (pgo.row, pgo.col) == (6, 33)
print("ok", len(list(Path("games/source").glob("*/*.*"))), "levels")
'
```

Live API check (example): start A001, confirm `grid_cols=33` and lit cells
with `col >= 24` in `led_display` / `GET /game-state/{game_id}`.

## Related docs

- [`SETTINGS.md`](./SETTINGS.md) — `value_high` / `value_width` / `floor_layout_coors_no_use`
- [`CODE_STUDY.md`](./CODE_STUDY.md) — legacy load + `group_size_scale` notes
- Sibling ports: Grid `docs/LEVELS.md`, Hoops `api/level_scaling.py`
