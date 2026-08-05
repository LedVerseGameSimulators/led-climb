# led-climb — Onsite Merge Notes (2026-08-03)

**Branch:** `merge/onsite-takeaway-2026-08-03`  
**Base:** `enhancement/level-scaling-6x33` @ `027b429`  
**Commit:** `807e77531e756d8e64f000678a2d8723a882e409`  
**Source zip:** `led-climb-takeaway-2026-08-03.zip`  
**Extract:** `.onsite-analysis/led-climb/led-climb/`

## Summary

Merged the largest substantive onsite takeaway: hardware I/O fixes on top of the
level-scaling / kiosk / group base. All planned TAKE files copied; local
`.gitignore` retained (tracks shelve). Venue `led_parameter.dat` applied with
`game_scode_divide_person/time = False`.

## Files changed (24)

### Modified (13)

| Path | Change |
|------|--------|
| `api/game_manager.py` | `unused_cells` from shelve; masked-goal grace (DK07/B31); HW+sim input merge; `_record_input_event`; `get_active_game`/`snapshot_games`; I/O timing stats |
| `api/main.py` | Active-game via `get_active_game()`; HW diagnostics (io ms avg/max) |
| `api/requirements.txt` | Added `httpx==0.28.1`, `pyserial==3.5` |
| `games/led/led_control.py` | Framed sensor parser integration; `HW_COLOR_ORDER`; wire clamp ≤254; non-blocking serial default |
| `games/led/communication.py` | Partial-write detection on serial send |
| `ws_bridge.py` | Poll `/game-state/{id}` ~20 Hz; forward full `state` (minus duplicate `led_display`); discovery interval |
| `frontend/src/screens/SimulatorScreen.jsx` | postMessage bridge state (no HTTP poll); event-driven `playPress`; group mode label |
| `simulator/static/index.html` | rAF coalesce (`scheduleDraw`); postMessage parent; glow default 0 |
| `scripts/start-dev.bat` | HW env vars |
| `tests/test_game_manager_level_scaling.py` | Updated for `unused_cells` in settings load |
| `games/setting/led_parameter.dat` | Venue values: `scode_divide_* = False` (was True locally) |
| `HARDWARE_VALIDATION.md` | Onsite validation notes |
| `ONSITE.md` | Onsite deploy notes |

### Added (11)

| Path | Purpose |
|------|---------|
| `games/led/sensor_protocol.py` | Framed `0xFC` sensor parser |
| `tests/test_sensor_protocol.py` | Parser unit tests (7 cases) |
| `tests/test_group_mode.py` | Group mode API tests (3 cases) |
| `START_GAME.bat` / `STOP_GAME.bat` | One-click operator start/stop |
| `scripts/run-api.bat`, `run-bridge.bat`, `run-ui.bat` | Individual service launchers |
| `HARDWARE_INTEGRATION_BUGS.md` | Bug catalog + mitigations |
| `OPERATOR_GUIDE.md` | Floor operator instructions |
| `PENDING_ISSUES.md` | Handoff tracker (statuses updated post-merge) |

### Kept local (not copied)

| Path | Reason |
|------|--------|
| `.gitignore` | Local tracks shelve; onsite ignores all `*.dat` |
| `api/level_scaler.py`, `docs/LEVEL_SCALING.md` | Identical per plan |
| Other FE screens | Identical per plan |
| `docs/SETTINGS.md` | Local correctly marks unused-row as implemented |
| `ledplaydb.sqlite` | Runtime DB — not committed |
| `frontend/.env` | Deploy-only RFID URL |

## Shelve diff

| Key | Local (pre-merge) | Onsite (merged) |
|-----|-------------------|-----------------|
| `game_scode_divide_person` | True | **False** |
| `game_scode_divide_time` | True | **False** |
| `list_com_info` | 3 ports (COM3/4/5) | Same |
| `list_no_use_position` | 7 entries (rows 0+5) | Same |

## Blockers

**None.** All TAKE files merged without conflict. Plan decisions applied:

- `scode_divide_*` → False (onsite venue behavior)
- `HW_COLOR_ORDER` → RGB (onsite default)
- Bridge + SimulatorScreen shipped together

No `MERGE_BLOCKERS.md` written.

## Test results

```
python3 -m pytest tests/test_sensor_protocol.py \
  tests/test_game_manager_level_scaling.py \
  tests/test_group_mode.py tests/test_level_scaler.py -v
```

**Result: 30 passed in 3.56s**

| Suite | Tests | Status |
|-------|-------|--------|
| `test_sensor_protocol.py` | 7 | PASS |
| `test_game_manager_level_scaling.py` | 5 | PASS |
| `test_group_mode.py` | 3 | PASS |
| `test_level_scaler.py` | 15 | PASS |

## PENDING_ISSUES status updates

| # | Issue | Post-merge status |
|---|-------|-------------------|
| 1 | Unused rows in completion | **Implemented** (`unused_cells`) |
| 2 | DK07 masked goals | **Implemented** (`permanently_green_masked` + grace) |
| 3 | UI lag / duplicate polling | **Implemented** (bridge postMessage stream) |
| 4 | Score-inferred sounds | **Implemented** (`input_events` ring) |
| 5 | Sensor frame alignment | **Implemented (headless)** — floor soak still owed |

## Hardware validation still owed

See `PENDING_ISSUES.md` checklist (A004, DK07, soak, RGB pure-color, etc.).

## Not pushed

Commit is local only per instructions.
