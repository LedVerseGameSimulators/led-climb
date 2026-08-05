# LED Climb — Pending Issues

Snapshot for takeaway / onsite handoff. Details and mitigations live in
[`HARDWARE_INTEGRATION_BUGS.md`](./HARDWARE_INTEGRATION_BUGS.md).

**Venue note:** floor is logical **6×33**; rows **0** and **5** are unused
(`floor_layout_coors_no_use`). Wired play area is **4×33 (132 tiles)**.
Hardware color order is **`HW_COLOR_ORDER=RGB`**. Do not change COM ports or
color order without a controlled pure-color test.

---

## Blockers for clean physical sessions

| # | Issue | Impact | Status |
|---|--------|--------|--------|
| 1 | Scoreable cells on unused rows 0/5 still counted in `remaining_scoreable` | Levels like **A004+** can never complete on the physical floor | **Implemented** — `unused_cells` filters scoring/completion (`is_active_cell`, completion loop) |
| 2 | Green priority permanently hides overlapping goals (e.g. **DK07**) | Goals stay unreachable; session cannot advance | **Implemented** — `permanently_green_masked` skip + `_MASKED_GOAL_GRACE` auto-clear (B31) |
| 3 | Simulator / UI lag under hardware play | Grid, score, lives can desync or freeze while floor stays responsive | **Implemented** — bridge polls `/game-state/{id}` ~20 Hz; sim forwards via postMessage |
| 4 | Tile sounds inferred from polled score/life deltas | Sounds delay, merge, or drop under load | **Implemented** — `_record_input_event` ring + SimulatorScreen event-driven `playPress` |
| 5 | Serial sensor parser can lose frame alignment | Presses near COM boundaries can shift/drop; out-of-range tile indices | **Implemented (headless)** — `sensor_protocol.py` framed parser + unit tests; **needs COM-boundary soak on floor** |

---

## Operator / packaging notes

- One-click start/stop: `START_GAME.bat` / `STOP_GAME.bat` — see `OPERATOR_GUIDE.md`.
- UI: <http://localhost:5175> · API: <http://localhost:8002> · bridge: <http://localhost:8766>.
- Venue shelve settings under `games/setting/` (`led_parameter.dat`,
  `debug_parameter.dat`, and matching `.bak`/`.dir`) are tracked in git for deploy.
- Level shelves / assets under `games/source/` must be present on the floor PC.
- MySQL connector warnings on API start are OK for headless/onsite without DB.

---

## Validation still owed on the floor

- [ ] A004 advances with no stuck goals on rows 0/5
- [ ] DK07 does not retain goals permanently masked by green
- [ ] Grid / score / lives stay in sync for rapid hardware play
- [ ] One ordered sound event per accepted press
- [ ] Sensor parser survives partial reads; no tile index ≥ 132
- [ ] Pure red / green / blue display correctly (RGB) with no flicker
- [ ] Bounded API/bridge traffic over a 10-minute session

---

## Not blocking daily start

- Result ranking / tourist DB paths unused without MySQL
- End-fragments, videos, wall/screen lights not in this headless build
- RFID/barcode session timer not wired
