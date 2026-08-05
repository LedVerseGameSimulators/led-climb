@echo off
cd /d "%~dp0.."
set "USE_SERIAL_HD=1"
set "HW_COLOR_ORDER=RGB"
set "HW_SERIAL_BLOCKING=0"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8002 --no-access-log
