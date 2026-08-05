@echo off
cd /d "%~dp0..\frontend"
call npm run dev -- --host 0.0.0.0 --port 5175
