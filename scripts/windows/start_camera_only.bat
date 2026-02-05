@echo off
REM Start only the Camera Server

cd /d "%~dp0\..\.."

echo Starting Camera Server only (port 5558)...
python -m src.launcher --service camera

pause
