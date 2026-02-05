@echo off
REM Start only the Control Manager (no camera, no UI)

cd /d "%~dp0\..\.."

echo Starting Control Manager only (port 5557)...
python -m src.launcher --service manager

pause
