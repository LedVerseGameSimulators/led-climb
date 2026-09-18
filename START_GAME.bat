@echo off
setlocal EnableExtensions
title LED Climb Launcher
cd /d "%~dp0"
set "ROOT=%CD%"

if not defined ACTIVERSE_KIOSK set "ACTIVERSE_KIOSK=1"

echo.
echo ==========================================
echo          LED CLIMB - START GAME
echo ==========================================
echo.

REM Prefer the installed Python 3.11 when a fresh Windows shell has not yet
REM picked it up in PATH.
where python >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
    ) else (
        echo ERROR: Python 3.11 is not installed.
        echo Install Python 3.11, then run START_GAME.bat again.
        goto :failed
    )
)

where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js/npm is not installed.
    echo Install Node.js LTS, then run START_GAME.bat again.
    goto :failed
)

if not exist "games\setting\led_parameter.dat" (
    echo ERROR: games\setting\led_parameter.dat is missing.
    echo Restore the venue floor settings before starting the game.
    goto :failed
)
if not exist "games\setting\debug_parameter.dat" (
    echo ERROR: games\setting\debug_parameter.dat is missing.
    echo Restore the venue debug settings before starting the game.
    goto :failed
)

echo Checking Python packages...
REM Use semicolons — commas inside python -c break some cmd parsers.
python -c "import fastapi; import uvicorn; import httpx; import serial" >nul 2>&1
if errorlevel 1 (
    echo Installing required Python packages...
    python -m pip install -r "api\requirements.txt"
    if errorlevel 1 goto :failed
)

if not exist "frontend\node_modules" (
    echo Installing frontend packages. This is needed only once...
    pushd "frontend"
    call npm install
    if errorlevel 1 (
        popd
        goto :failed
    )
    popd
)

REM Do not put parentheses in echo text inside this IF — cmd treats ) as end-of-block.
if not exist "frontend\.env" (
    if exist "frontend\.env.example" (
        echo Creating frontend\.env from example for RFID...
        copy /Y "frontend\.env.example" "frontend\.env" >nul
    )
)

echo Stopping any previous LED Climb copy...
call "%ROOT%\STOP_GAME.bat" /quiet
ping -n 2 127.0.0.1 >nul

echo Starting floor engine - hardware mode...
start "LED Climb API" /MIN /D "%ROOT%" cmd.exe /k call "scripts\run-api.bat"

echo Starting simulator bridge...
start "LED Climb Bridge" /MIN /D "%ROOT%" cmd.exe /k call "scripts\run-bridge.bat"

echo Starting operator interface...
set "WINDOW_TITLE_UI=LED Climb UI"
call "%ROOT%\scripts\kiosk\run-ui-prod.bat" 5175
if errorlevel 1 goto :failed
ping -n 5 127.0.0.1 >nul

echo Waiting for game UI...
set /a _tries=0

:wait_ui
set /a _tries+=1
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:5175/' -UseBasicParsing -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto ui_ready
if %_tries% GEQ 30 goto ui_timeout
ping -n 2 127.0.0.1 >nul
goto wait_ui

:ui_timeout
echo WARNING: UI did not respond yet. Opening browser anyway.
goto check_services

:ui_ready
echo UI is ready.

:check_services
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing 'http://localhost:8002/health' -TimeoutSec 3; if ($r.StatusCode -ne 200) { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo ERROR: The floor engine did not start.
    echo Check the minimized LED Climb API window for details.
    goto :failed
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing 'http://localhost:8766/status' -TimeoutSec 3; if ($r.StatusCode -ne 200) { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo ERROR: The simulator bridge did not start.
    echo Check the minimized LED Climb Bridge window for details.
    goto :failed
)

call "%ROOT%\scripts\kiosk\open-ui.bat" 5175 climb

echo.
echo ==========================================
echo   LED CLIMB is running
echo   Open:  http://127.0.0.1:5175/
echo   Ctrl+Shift+K exits fullscreen kiosk
echo   To stop: double-click STOP_GAME.bat
echo ==========================================
echo.
exit /b 0

:failed
echo.
echo START FAILED. Read the error above or see OPERATOR_GUIDE.md.
echo See OPERATOR_GUIDE.md for common fixes.
exit /b 1
