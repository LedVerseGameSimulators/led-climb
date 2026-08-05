# LED Climb Operator Guide

This guide is for daily operation of LED Climb. No development commands are
required.

## Start the game

1. Make sure the LED floor controllers and USB serial connections are powered.
2. Double-click **`START_GAME.bat`** in the LED Climb folder.
3. Wait while the launcher checks the computer and starts three minimized
   windows:
   - **LED Climb API** — floor engine and physical hardware;
   - **LED Climb Bridge** — simulator updates;
   - **LED Climb UI** — operator interface.
4. The browser opens automatically at <http://localhost:5175>.
5. Leave the three minimized windows running while the game is in use.

The first start on a newly prepared computer may install frontend packages and
take several minutes. Later starts should take only a few seconds.

## Stop the game

1. Finish the current player session if possible.
2. Double-click **`STOP_GAME.bat`**.
3. Wait for the message that LED Climb has stopped.

Always use `STOP_GAME.bat` before switching off the floor computer. It ends the
active session and sends a black frame to the physical LEDs before closing the
services.

## Normal addresses

- Operator interface: <http://localhost:5175>
- Floor engine health: <http://localhost:8002/health>
- Simulator bridge status: <http://localhost:8766/status>

## Common fixes

### Browser did not open

Open Chrome or Edge and visit <http://localhost:5175>.

### START GAME reports missing Python or Node.js

Ask technical support to install:

- Python 3.11;
- Node.js LTS.

Then double-click `START_GAME.bat` again.

### Floor settings are missing

Do not run the game without the venue settings. Restore these files under
`games\setting`:

- `led_parameter.dat`;
- `debug_parameter.dat`;
- their matching `.bak` and `.dir` files when present.

### Interface opens but does not update

1. Double-click `STOP_GAME.bat`.
2. Wait five seconds.
3. Double-click `START_GAME.bat`.
4. Refresh the browser once.

### Physical floor does not respond

1. Stop LED Climb.
2. Check that all three USB serial cables are connected.
3. Check floor controller power.
4. Start LED Climb again.
5. If the problem remains, record the message in the minimized
   **LED Climb API** window and contact technical support.

### Wrong colors or flickering

Stop the game and contact technical support. Do not change COM ports or
`HW_COLOR_ORDER`; this venue is configured for RGB.

## Operator rules

- Run only one copy of LED Climb. `START_GAME.bat` automatically closes an old
  copy before starting.
- Do not close the minimized service windows during play.
- Do not edit files in `games\setting`.
- Do not unplug USB serial cables while a game is running.
- Use `STOP_GAME.bat` at the end of operation.
