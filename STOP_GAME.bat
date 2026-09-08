@echo off
setlocal EnableExtensions
title LED Climb Shutdown
cd /d "%~dp0"

echo.
echo ==========================================
echo           LED CLIMB - STOP GAME
echo ==========================================
echo.
echo Ending the active game and blanking the floor...

REM Ask the API to stop cleanly first so the physical LEDs receive a black
REM frame before any process is terminated.
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $a=Invoke-RestMethod 'http://localhost:8002/active-game' -TimeoutSec 2; if ($a.success) { $body=@{card_id=$a.card_id;game_id=$a.game_id}|ConvertTo-Json -Compress; Invoke-RestMethod -Method Post -Uri 'http://localhost:8002/logout' -ContentType 'application/json' -Body $body -TimeoutSec 4 | Out-Null } } catch {}" >nul 2>&1
REM ping-wait works under agent shells; timeout.exe fails with redirected stdin
ping -n 2 127.0.0.1 >nul

echo Stopping floor engine, bridge, and interface...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports=8002,8766,5175; Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort } | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }" >nul 2>&1
taskkill /FI "WINDOWTITLE eq LED Climb API*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq LED Climb Bridge*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq LED Climb UI*" /T /F >nul 2>&1

echo.
echo LED Climb has stopped.
ping -n 3 127.0.0.1 >nul
exit /b 0
