@echo off
cd /d "%~dp0.."
set "API_PORT=8002"
set "WS_BRIDGE_PORT=8766"
python ws_bridge.py
