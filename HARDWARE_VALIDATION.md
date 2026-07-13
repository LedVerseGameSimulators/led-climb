# Hardware Validation Status — LED Climb

**Last updated:** 2026-07-13

This document is the source of truth for "what's actually been tested on
real hardware vs. implemented-but-unverified" for the Climb game. Read
this before any on-site hardware session.

---

## 1. What hardware integration exists

- **Grid:** 6 rows × 33 cols (square single-color tiles — not hex, no
  concentric rings).
- **COM ports:** typically 3 serial ports (`list_com_info` in the
  `games/setting/led_parameter` shelve — one entry per port, format
  `['COM_name', start_idx, end_idx, normal_led]`). Confirm actual count
  on-site by reading the shelve (see checklist below); 3 is the dev-time
  default, not a hard constraint.
- **Mechanism:**
  - `USE_SERIAL_HD` — env var (`api/game_manager.py`), `"1"` = real
    serial hardware, unset/`"0"` = mocked (`serial`/`led`/`led.led_control`
    modules replaced with `MagicMock()` so the same code runs headless in
    dev/sim).
  - `_hw_init()` (`api/game_manager.py`) — on first use, reads
    `list_com_info`, `led_layout_type`, `floor_layout_coors_no_use`,
    `value_high`/`value_width` from the `led_parameter` shelve, then calls
    `led_control.init_layout(...)` and `led_control.init_com(...)` to open
    the serial ports and build the coordinate-mapping table.
  - Per-frame draw — inside the game loop's frame callback, gated by
    `USE_SERIAL_HD and _hw_led_control is not None`, throttled by
    `_HW_DRAW_INTERVAL` (default 0.045s ≈ 22fps) so as not to saturate
    serial. Calls `_hw_led_control.draw_screen_by_com(_hw_layout_type,
    grid)` to push the current frame, and
    `_hw_led_control.update_screen_state_by_com(...)` to read sensor state
    back.
  - `_hw_blank_floor(led_table)` (added this session) — sends one
    all-`[0,0,0]` frame via the same `draw_screen_by_com` call, gated the
    same way. Wired into every game-end/stop path (see Section 3).

## 2. Validation history

- **Real hardware test, pre-rework:** Climb was one of only two games
  (the other is led-hoops) actually run on a physical LED floor. That
  validation happened around commit `338392a` ("Hardware integration: fix
  decompiler slice bugs + add USE_SERIAL_HD mode", 2026-06-30) — the
  `_hw_init()` / `USE_SERIAL_HD` mechanism and the per-frame
  `draw_screen_by_com` / `update_screen_state_by_com` calls are real,
  working code as of that snapshot, not speculative.
- **Since then — NOT re-validated:** this development session added the
  cross-tier marathon loop, 5-heart lives display, RFID card-scan login,
  credit-gated sessions, pushable settings, a persistent player badge, and
  real 2P via DK-series levels (checkerboard blue=P1/orange=P2 scoring).
  None of this gameplay rework has been run against the physical floor.
  The hardware *driver* code itself was untouched by that rework (it sits
  below the gameplay layer), but the surrounding session lifecycle it
  hooks into changed significantly, so end-to-end behavior on real
  hardware is unconfirmed.
- **Blank-on-stop fix — code-only, unvalidated:** this session also added
  a fix for a known bug (floor stays lit with the last frame after a
  session ends — see git history / led-hoops'
  `docs/TODO_HARDWARE_BLANK_ON_STOP.md` for the original writeup, which
  flagged the bug as applicable to all 5 games). The fix is implemented
  and syntax-checked but **has never run against a physical floor.**

## 3. Blank-on-stop fix — what was added

`_hw_blank_floor(led_table)` in `api/game_manager.py`, called at every
point a session/game actually ends:

1. **No-levels early exit** — `start_game()`'s `_run_game()`, if
   `play is None or not game.level_sequence`.
2. **Normal session end** — after the marathon loop exits (timer expired,
   life exhausted, or level sequence completed), right after
   `game.update_state(game_over=True, ...)`.
3. **Exception path** — the `_run_game()` `except Exception` handler
   (best-effort; `game.led_table` may still be `None` if the crash
   happened before setup completed).
4. **`stop_game()`** — manual stop, reached via `/logout` (and any future
   explicit stop endpoint).
5. **`clear_all()`** — called at the start of every `create_game()`
   (kiosk model: starting a new game first clears any prior one). Blanks
   every game being cleared, not just one.

All 5 call sites reuse the exact same `draw_screen_by_com` call already
used for normal frames, just with an all-`[0,0,0]` grid, gated behind
`USE_SERIAL_HD and _hw_led_control is not None` exactly like the existing
per-frame draw.

**This cannot be validated without a physical floor.** Code review confirms
it's wired into every known exit path and reuses proven draw plumbing, but
onsite testing must confirm the floor actually goes dark, that there's no
race with the game thread's own in-flight write, and that a single blank
write is reliable (some panels have shown single-write drops in prior
on-site testing per other games' hardware notes — if Climb shows the same
symptom, consider sending the blank frame 2-3 times).

## 4. Onsite validation checklist

Run through this on the real Climb floor before opening to players.

**Setup**
- [ ] Start the API with `USE_SERIAL_HD=1` (see `ONSITE.md` Step 8).
      Confirm log line `Hardware ready: N port(s), 6×33, layout=X`.
- [ ] Run `games/test_hardware.py` (`python test_hardware.py` from
      `games/`). Confirm: all COM ports open OK, full 6×33 floor lights
      **green** for 3s, stepping on tiles prints `PRESS detected: row=X
      col=Y`, floor clears to black at the end.

**Grid mapping**
- [ ] Spot-check the four corners: (row=0,col=0), (row=0,col=32),
      (row=5,col=0), (row=5,col=32) — confirm each lights the physically
      correct corner tile, not a mirrored/rotated one.
- [ ] Spot-check 3-4 interior cells (e.g. row=2/3, col=10/16/22) — confirm
      no off-by-one or serpentine-mapping drift between COM-port
      boundaries.

**Full gameplay**
- [ ] Play one full marathon session end-to-end on real hardware:
      login → level select → countdown → play through multiple levels
      (a-series/b-series) until session end (timer, life-exhausted, or
      full clear) → result screen.
- [ ] Play at least one real 2P DK-series level (e.g. DK01-DK10) with two
      players on the physical floor. Confirm the checkerboard split
      (P1=blue, P2=orange, alternating per-cell for same-color levels
      like DK03) displays correctly on the **physical floor**, not just
      the simulator — this is genuine 2P (unlike, e.g., a game where 2P
      only works in the browser simulator).

**Blank-on-stop**
- [ ] Let a session run out the clock (no life loss) → confirm the floor
      goes fully dark within ~1s of the simulator showing the result
      screen.
- [ ] Force life to 0 mid-session → confirm floor blanks on game-over.
- [ ] Manually trigger logout / stop mid-session → confirm floor blanks.
- [ ] Start a new game while a stale pattern is still showing (skip the
      above steps once to leave the floor lit) → confirm `clear_all()`'s
      blank fires before the new game's first real frame is drawn.
- [ ] Confirm no regression: floor still draws normally during active
      gameplay (throttle/lock unaffected by the blank-floor addition).

**Docs**
- [ ] `docs/STATUS_HARDWARE.md` and `docs/HARDWARE_MODE.md` currently
      contain misplaced led-hexagon content (16×26 grid, 3-ring hex
      tiles) — `docs/README.md` already flags this ("Hex grid — adapt for
      6×33"). If time allows onsite, rewrite these two files for Climb's
      real 6×33 single-color-tile protocol; otherwise treat this
      document and `ONSITE.md` as the authoritative source until they're
      fixed.
