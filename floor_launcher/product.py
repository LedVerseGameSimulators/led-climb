"""Per-product constants. This is the only file that differs between game repos."""

SLUG = "climb"            # kiosk profile slug (open-ui.bat ... climb), release/zip names
DISPLAY_NAME = "LED Climb"
API_PORT = 8002           # must match frontend/src/config.js (source of truth)
BRIDGE_PORT = 8766
# Ports freed on STOP (same set STOP_GAME.bat frees; 5175 = legacy vite preview UI).
STOP_PORTS = (8002, 8766, 5175)
