@echo off
REM Start Climb dev stack (API 8002, ws_bridge 8766, UI 5175).
setlocal
cd /d "%~dp0.."

echo ==^> LED Climb dev stack from %CD%

start "LED Climb API" cmd /k "cd /d %CD% && set USE_SERIAL_HD=1 && set HW_COLOR_ORDER=RGB && set HW_SERIAL_BLOCKING=0 && python -m uvicorn api.main:app --host 0.0.0.0 --port 8002 --no-access-log"
timeout /t 2 /nobreak >nul
start "LED Climb ws_bridge" cmd /k "cd /d %CD% && set API_PORT=8002 && set WS_BRIDGE_PORT=8766 && python ws_bridge.py"
timeout /t 2 /nobreak >nul
start "LED Climb Frontend" cmd /k "cd /d %CD%\frontend && npm run dev"

echo.
echo Climb ready:
echo   UI:        http://localhost:5175
echo   API:       http://localhost:8002
echo   ws_bridge: http://localhost:8766
echo.
echo Close the three command windows to stop the stack.
endlocal
