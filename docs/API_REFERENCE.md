# API Reference — LED Climb (`api/main.py`)

Lightweight endpoint reference for developers/on-site agents. Not a full
OpenAPI spec — just enough to know what this backend exposes at a glance.
Base it against `api/main.py` directly if you need exact behavior; models
are in `api/models.py`.

---

## Game lifecycle

### `POST /login`
Look up a player by RFID card ID.
- **Body:** `{ card_id: str }`
- **Response:** `{ success, player: { custom_id, name, phone, time_left (sec), card_id }, error? }`

### `POST /start-game`
Create and start a new game session. Clears any prior game first (kiosk
model — see `clear_all()`).
- **Body:** `{ card_id: str, level: int|str (numeric or "DK01"-style), difficulty: "easy"|"normal"|"hard" }`
- **Response:** `{ success, game_id, ws_url ("/game/{game_id}"), error? }`
- Fails with `error: "Session time expired (60-minute limit)"` if the
  card's remaining session time (from the DB) is `<= 0`.

### `WS /game/{game_id}`
Real-time game state stream. Sends `{ type: "game_state", data: <state> }`
at ~60fps while `game.running`; accepts input JSON from the client
(currently logged but not yet wired to `Play.py` — actual input goes
through `/game-input` below). Closes with code `1008` if the game_id
doesn't exist.

### `GET /game-state/{game_id}`
State of one specific game (what the simulator polls for its own game).
- **Response:** `{ success, game_id, state: {...} }` or `{ success: false, error }`

### `GET /game-state`
State of the first active game (no game_id needed) — legacy/simple case.
- **Response:** `{ success, game_id, state }` or `{ success: false, error: "No active games" }`

### `GET /active-game`
Resume-on-reload: returns the currently-running game's full config so the
frontend can restore the simulator instead of restarting at login.
- **Response:** `{ success, game_id, card_id, level, difficulty, state }` or `{ success: false }`

### `POST /game-input`
Player input: press/release a tile.
- **Body:** `{ row: int, col: int, type: "press"|"release", game_id?: str }` — `game_id` optional, defaults to the first active game.
- **Response:** `{ success, score }`

### `GET /result/{game_id}`
Result + leaderboard after a game ends (works even after the game object
is cleaned up, returning an empty state in that case).
- **Response:** `{ success, score, player_name, time_used, difficulty, leaderboard: [{rank, name, score, timestamp}], error? }`

### `POST /save-score`
Persist a finished session to the leaderboard DB.
- **Body:** `{ card_id, card_id2?, multiplayer?, level, end_level, score, score2?, final_score, final_score2?, life, lives_start, result, time_used, levels_cleared, difficulty, started_at }`
- **Response:** `{ success, error? }`

### `POST /logout`
End a game session (calls `stop_game()`, which now also blanks the
physical floor — see `HARDWARE_VALIDATION.md`) and records a basic score
entry.
- **Body:** `{ card_id: str, game_id: str }`
- **Response:** `{ success, error? }`

### `GET /levels`
List all Climb levels grouped by series: `a-series` (1P, `.led`,
A001-A025), `b-series` (1P, `.led`, B01-B31), `dk-series` (2P, `.ledb`,
DK01-DK10).
- **Response:** `{ success, levels: [{id, name, path, category, multiplayer, file_type}], categories: {a-series:[...], b-series:[...], dk-series:[...]}, count }`

---

## RFID / settings

### `POST /settings`
Runtime overrides pushed from the central RFID server (default difficulty,
session length). Written to `games/setting/runtime_overrides.json`; does
**not** touch the original read-only `led_parameter` shelve.
- **Body:** `{ default_difficulty?: str, session_minutes?: int }`
- **Response:** `{ success, overrides: {...} }`

### `GET /settings`
Current runtime overrides (empty object if none set yet).
- **Response:** contents of `runtime_overrides.json`, or `{}`

### `GET /game-settings`
Loads settings from a hardcoded legacy shelve path (`led_parameter` under
an old hexagon clone path) with hardcoded 16×26 fallback defaults —
**this endpoint's defaults do not reflect Climb's real 6×33 grid.** Left
as-is per scope of this task; flagged here for awareness, not fixed.
- **Response:** `{ success, wall_layout, grid_dims: {rows, cols}, timeout_seconds, max_score }`

### `GET /hw-debug`
Live hardware loop diagnostics — whether `USE_SERIAL_HD` is on, per-game
running/score/hw-draw-count/last-draw-time, and any zombie threads.
- **Response:** `{ use_serial_hd, active_games, games: [{game_id, running, score, hw_draw_count, last_hw_draw}], zombie_threads }`

---

## Scores

### `GET /scores?since=<ISO timestamp>`
Scores recorded after `since` (default `2000-01-01T00:00:00`). Used by the
central RFID server's cross-game leaderboard poller.
- **Response:** `{ success, game, scores: [...] }`

### `GET /leaderboard/{level}?limit=10`
Top scores for a specific level.
- **Response:** `{ success, level, entries: [...] }`

---

## Misc

### `GET /health`
Basic health check + game manager stats.
- **Response:** `{ status: "ok", game, stats }`
