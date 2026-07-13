# Onsite Agent Prompt — LED Climb

Copy everything below this line and hand it to a fresh Claude Code agent
running on the physical Windows machine, after this repo's zip has been
extracted there.

---

You are running on a **Windows** machine at the venue, inside a freshly
extracted copy of the `led-climb` repo. Assume the repo lives at
`C:\activerse\led-climb` (this matches what `ONSITE.md` assumes — if the
zip was actually extracted somewhere else, adjust every path below
accordingly, but keep the rest of the plan the same).

This is Windows: use `python` (not `python3`), use Command Prompt/PowerShell
syntax (not bash) — e.g. `set VAR=value` not `export VAR=value`, `cmd`
scripts (`.bat`), backslash paths. `ONSITE.md` already assumes Command
Prompt run as Administrator — follow that convention throughout.

## Read these three files first, in this exact order

1. **`ONSITE.md`** — single-machine setup: extracting the zip, checking
   Python, installing dependencies, verifying the `led_parameter` shelve,
   verifying COM ports, running the hardware diagnostic script, starting
   all services. This is your primary setup runbook.
2. **`ONSITE_LAN_INTEGRATION_PLAN.md`** — cross-machine network setup.
   This machine is one of 6 on a shared LAN (5 game floors + a central
   RFID/reception server). Read this to understand static IP assignment,
   port map, firewall rules, and how this machine's `/scores` and
   `/validate` calls interact with the other 5. Do NOT reconfigure other
   machines from here — this document only tells you what THIS machine
   needs (its own static IP, its own firewall rule for its API port, and
   which central RFID server IP to point at).
3. **`HARDWARE_VALIDATION.md`** — what specifically needs testing on the
   real floor: what hardware integration exists, what has and hasn't been
   validated on real hardware, and a concrete checklist.

Do not skip ahead to running commands before reading all three — the
LAN plan changes some `localhost` defaults to real IPs, and the hardware
validation doc tells you what "success" actually looks like for each
step (not just "no error thrown").

## What to do

1. Execute the setup in `ONSITE.md` step by step, in order. Do not skip
   verification steps it calls out (checking Python, checking the shelve
   contents, checking COM ports before starting services). Do not touch
   the RFID server, SQL server, or any other service already running on
   this PC, per `ONSITE.md`'s own warning.
2. Apply the network changes from `ONSITE_LAN_INTEGRATION_PLAN.md` that
   apply to this machine (Climb): static IP, firewall rule for its API
   port, and pointing at the correct central RFID server address instead
   of `localhost`.
3. Start the game with `USE_SERIAL_HD=1` as `ONSITE.md` Step 8 describes.
4. Work through the **Onsite validation checklist** in
   `HARDWARE_VALIDATION.md` section 4, in order:
   - Setup (hardware-ready log line, `games/test_hardware.py` diagnostic)
   - Grid mapping (corners + interior spot checks)
   - Full gameplay (one complete marathon session end-to-end, plus one
     real 2P DK-series level with two players on the physical floor —
     confirm the checkerboard blue=P1/orange=P2 split renders correctly
     on the real floor, not only in the browser simulator)
   - Blank-on-stop (floor goes dark on timeout, on life-exhausted,
     on manual stop/logout, and before a new game's first frame after
     `clear_all()`)

## How to report back

Do not just say "done" or "setup complete." For every checklist item in
`HARDWARE_VALIDATION.md` section 4, report explicit **pass/fail** status,
e.g.:

```
Setup:
  [PASS] USE_SERIAL_HD=1, log showed "Hardware ready: 3 port(s), 6×33, layout=5"
  [PASS] test_hardware.py: all 3 COM ports opened, floor lit green, presses detected on 4/4 tested tiles
Grid mapping:
  [PASS] corners (0,0)/(0,32)/(5,0)/(5,32) all correct
  [FAIL] interior cell (row=3,col=16) lit one column off — looks like an off-by-one at COM port boundary; investigate list_com_info index ranges
Full gameplay:
  [PASS] full marathon session (A001->A007, timeout end) ran clean on hardware
  [FAIL] DK03 2P level: P2 orange tiles did not light on physical floor, only in simulator — investigate before going live
Blank-on-stop:
  [PASS] timeout blanks floor within ~1s
  [PASS] life-exhausted blanks floor
  [PASS] manual stop/logout blanks floor
  [PASS] clear_all() blanks stale pattern before new game's first frame
```

If something fails, include enough detail (log lines, what you observed
on the floor, which COM port/cell) that it can be fixed without another
onsite trip. If everything genuinely passes, still enumerate each item
individually rather than a single blanket "all good."
