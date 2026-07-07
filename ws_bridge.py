"""
WebSocket bridge: headless API game state → simulator UI
Connects to http://localhost:8000 API, broadcasts game state via WebSocket
"""

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import httpx

app = FastAPI()

# Serve static simulator files
SIMULATOR_STATIC = str(Path(__file__).resolve().parent / "simulator" / "static")
app.mount("/static", StaticFiles(directory=SIMULATOR_STATIC), name="static")

HOST = "127.0.0.1"
_DEFAULT_API_PORT = 8002
_DEFAULT_WS_PORT = 8766
API_PORT = int(os.getenv("API_PORT", _DEFAULT_API_PORT))
PORT = int(os.getenv("WS_BRIDGE_PORT", _DEFAULT_WS_PORT))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://localhost:{API_PORT}")

class GameBridge:
    """Bridge between API and WebSocket clients"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.lock = asyncio.Lock()
        self.current_game_id = None
        self.game_state = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.active_connections.add(ws)
        print(f"[OK] Client connected. Total: {len(self.active_connections)}")

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            self.active_connections.discard(ws)
        print(f"[OK] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast_state(self, game_state: dict):
        """Send game state to clients. Climb = SQUARE grid, SINGLE RGB per cell."""
        if not self.active_connections:
            return

        # Climb: led_display is flat list of [R,G,B] single colors.
        # Grid dims come from the API (6x33 for Climb); default to those.
        led_display = game_state.get("led_display", [])
        rows = int(game_state.get("grid_rows", 6))
        cols = int(game_state.get("grid_cols", 33))

        def _rgb(cell):
            if isinstance(cell, (list, tuple)) and len(cell) >= 3:
                # single [r,g,b]
                if not isinstance(cell[0], (list, tuple)):
                    return [int(cell[0]), int(cell[1]), int(cell[2])]
                # legacy 3-ring -> take middle ring
                mid = cell[1] if len(cell) > 1 else cell[0]
                return [int(mid[0]), int(mid[1]), int(mid[2])]
            return [0, 0, 0]

        grid = []
        if led_display and len(led_display) == rows * cols:
            for i in range(rows):
                grid.append([_rgb(led_display[i * cols + j]) for j in range(cols)])
        else:
            grid = [[[0, 0, 0] for _ in range(cols)] for _ in range(rows)]

        msg = json.dumps({
            "type": "frame",
            "rows": rows,
            "cols": cols,
            "grid": grid,
            "fps": 60,
            "game_id": self.current_game_id
        })

        async with self.lock:
            dead = set()
            for ws in self.active_connections:
                try:
                    await ws.send_text(msg)
                except Exception as e:
                    print(f"[ERR] Send error: {e}")
                    dead.add(ws)
            self.active_connections -= dead

    async def broadcast_blank(self, rows: int, cols: int):
        if not self.active_connections:
            return
        msg = json.dumps({
            "type": "frame",
            "rows": rows,
            "cols": cols,
            "grid": [[[0, 0, 0]] * cols for _ in range(rows)],
            "fps": 30,
            "game_id": None,
        })
        async with self.lock:
            dead = set()
            for ws in self.active_connections:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.add(ws)
            self.active_connections -= dead

bridge = GameBridge()

@app.get("/")
async def index():
    """Serve simulator UI"""
    return FileResponse(f"{SIMULATOR_STATIC}/index.html")

@app.get("/status")
async def status():
    """Health check"""
    return {
        "status": "ok",
        "game_id": bridge.current_game_id,
        "game_state": bridge.game_state,
        "connected_clients": len(bridge.active_connections)
    }

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for simulator UI"""
    client_game_id = ws.query_params.get("game_id")
    await bridge.connect(ws)
    async with httpx.AsyncClient() as client:
        try:
            while True:
                # Client sends tile commands: {type:'press'|'release', row, col}
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                    if data.get("type") in ("press", "release"):
                        # Forward to API game-input endpoint
                        await client.post(
                            f"{API_BASE_URL}/game-input",
                            json={
                                "row": data.get("row"),
                                "col": data.get("col"),
                                "type": data["type"],
                            },
                            timeout=2,
                        )
                except Exception as e:
                    print(f"[ERR] Input forward error: {e}")
        except WebSocketDisconnect:
            await bridge.disconnect(ws)

async def poll_game_state():
    """Poll API for game state and broadcast to clients"""
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Get active game state from API
                resp = await client.get(f"{API_BASE_URL}/active-game", timeout=5)
                data = resp.json()

                if data.get("success"):
                    bridge.current_game_id = data["game_id"]
                    bridge.game_state = data["state"]
                    await bridge.broadcast_state(bridge.game_state)
                else:
                    bridge.current_game_id = None
                    bridge.game_state = {}
                    await bridge.broadcast_blank(6, 33)

                await asyncio.sleep(0.033)

            except Exception as e:
                print(f"[ERR] Poll error: {e}")
                await asyncio.sleep(1)

@app.on_event("startup")
async def _start_poller():
    """Run poller in uvicorn's own event loop (same loop as websockets).
    Avoids cross-loop 'bound to a different event loop' errors."""
    asyncio.create_task(poll_game_state())

if __name__ == "__main__":
    print(f"WS Bridge: {HOST}:{PORT}")
    print(f"API: {API_BASE_URL}")
    print(f"Web UI: http://{HOST}:{PORT}")

    # Start WebSocket server (poller launches via startup event)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
