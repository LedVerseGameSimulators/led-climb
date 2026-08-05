# Hardware Integration Bugs and Mitigation Plan

This document records the issues found during the first LED Climb hardware
integration session. The physical floor plays smoothly, but the simulator,
frontend telemetry, input audio, and some level-completion paths do not yet
faithfully represent the hardware.

## Confirmed floor geometry

- The game uses a logical 6×33 coordinate space.
- Venue settings mark every coordinate in logical rows 0 and 5 as unused.
- The wired floor is therefore rows 1–4 across 33 columns: 132 active tiles.
- Current level files were authored primarily in a 6×24 play area. Many contain
  scoreable cells on logical rows 0 and 5.
- The unused rightmost 9×4 area seen in early levels comes from the 24-column
  level content running on a 33-column floor; it is not a dead panel.

## 1. Unreachable scoreable cells block level completion

### Evidence

- A001–A003 can clear, while A004 is the first A-series level containing static
  scoreable cells on unused rows 0 and 5.
- A004 contains nine such cells. Most later A, B, and DK levels contain similar
  cells.
- The simulator renders the full logical 6×33 grid, so these cells can appear
  scoreable even though no corresponding physical tile exists.
- `remaining_scoreable` counts all scoreable group members without excluding
  `floor_layout_coors_no_use`.

### Effect

The physical player cannot consume these cells, but they remain in the
completion count. Affected levels eventually have no reachable goals while
`remaining_scoreable` stays above zero and the session cannot advance.

### Mitigation

Create one authoritative active-coordinate set from
`floor_layout_coors_no_use`, then apply it consistently to:

1. frame classification and `led_display`;
2. `goal_cells`, hazard cells, and input acceptance;
3. `remaining_scoreable` and auto-jump decisions;
4. simulator rendering.

Unused cells should remain black and must never participate in scoring or level
completion. Long term, levels can be redesigned for 4×33; filtering is the safe
compatibility behavior for existing 6×24 content.

## 2. Green priority can hide goals permanently

### Evidence

- Cell classification gives green groups higher priority than blue/orange goal
  groups.
- Hidden goals remain in their source groups and therefore remain in
  `remaining_scoreable`.
- Auto-jump only searches for a future wave. It does not resolve goals in the
  current wave that are permanently masked by green.
- DK07 contains six static orange cells that overlap static green cells for the
  full level window. B31 also contains risky moving-goal/green overlap.

### Effect

The floor and simulator correctly show green and presses correctly do nothing,
but the invisible goals can prevent completion forever.

### Mitigation

Completion must count reachable, priority-winning goals rather than raw source
members. Permanently masked cells should be treated as non-scoreable for the
current frame/wave. Auto-jump must also be able to advance past an exhausted
current wave instead of requiring a strictly future group start.

## 3. Simulator and frontend lag or freeze

### Evidence

- `ws_bridge.py` polls `/active-game` and full game state at about 30 Hz.
- React independently polls game state every 100 ms.
- More than 16,000 `/active-game` requests appeared during the test session.
- React uses `setInterval` without preventing overlapping in-flight requests.
- The iframe resizes its canvas and rebuilds gradients, rounded paths, shadows,
  and labels for all 198 logical cells on every frame.
- Grid frames and score/lives are delivered through separate polling paths, so
  they can become visibly out of sync.
- Uvicorn access logging amplifies the cost of this request volume.

### Effect

The physical game thread remains responsive, while the browser main thread and
HTTP polling pipeline build a backlog. The grid, score, lives, and controls then
appear delayed or stuck.

### Mitigation

1. Use one pushed WebSocket state stream for grid and telemetry.
2. Remove duplicate full-state polling, or retain only a low-rate guarded
   fallback.
3. Prevent overlapping requests with an in-flight guard/abort timeout.
4. Coalesce browser drawing with `requestAnimationFrame`.
5. Resize the canvas only when its display size or grid dimensions change.
6. Cache or simplify expensive visual effects and hide coordinate labels unless
   explicitly enabled.
7. Disable high-volume access logs in the normal onsite startup command.

## 4. Tile sounds are not event-driven

### Evidence

- The frontend receives no explicit tile-press or scoring event.
- Sounds are inferred from changes in score/lives observed by 100 ms polling.
- Several presses between polls collapse into one observed score change.
- Non-scoring tile presses cannot produce sound through this mechanism.

### Effect

Sounds are delayed, merged, or lost whenever polling or rendering lags.

### Mitigation

Publish monotonic press/scoring event identifiers with the game state (or a
small event queue). The frontend should play one sound per unseen event after
the browser audio context has been unlocked by a user gesture.

## 5. Serial sensor parser loses packet alignment

### Evidence

- Hardware logs show malformed payloads and attempts to index tile 132 in a
  valid 0–131 map.
- The current parser can treat a packet length byte as sensor payload after a
  split or partial serial read.
- Large malformed-packet dumps further increase latency.

### Effect

Presses near packet/COM boundaries can be shifted or dropped even though most
hardware input continues to work.

### Mitigation

Replace split-based parsing with a persistent framed parser:

1. retain incomplete bytes between reads;
2. search for the `0xFC` frame header;
3. validate the declared payload length;
4. consume exactly one complete frame at a time;
5. reject out-of-range tile indices without mutating state;
6. log compact counters/rate-limited samples instead of full payload dumps.

Add parser tests for split frames, concatenated frames, garbage prefixes,
invalid lengths, and each COM segment boundary.

## 6. Hardware color and coordinate discrimination

Simulator and hardware consume the same logical `led_display`. A sustained
same-coordinate color difference therefore comes from wire color encoding,
physical coordinate mapping, or stale hardware output—not separate game render
trees.

`HW_COLOR_ORDER=RGB` is the current onsite setting. Changing it without a
controlled pure-color test is unsafe because the earlier RBG trial turned green
output blue. Coordinate tests should compare a known logical cell with the
sensor row/column reported when that exact physical tile is pressed.

## Implementation order

1. Filter unused coordinates from rendering, scoring, and completion.
2. Make completion use reachable priority-winning goals.
3. Repair and test framed serial input parsing.
4. Consolidate simulator and telemetry delivery into one pushed stream.
5. Optimize canvas rendering and add request backpressure.
6. Add explicit press/scoring events and event-driven audio.
7. Re-run A004, DK07, COM-boundary, color-order, and sustained-play tests on the
   physical floor.

## Validation gates

- A004 advances without simulator-only goals on rows 0 or 5.
- DK07 cannot retain goals hidden permanently by green.
- Simulator grid, score, and lives remain synchronized during rapid hardware
  play.
- Every accepted hardware press produces one ordered event; scoring sounds are
  not inferred from polling.
- Sensor parsing reports no out-of-range tile index and survives partial reads.
- API/bridge request volume remains bounded during a 10-minute session.
- Pure red, green, and blue display correctly with no flicker.
