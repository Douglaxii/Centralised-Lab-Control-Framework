@echo off
REM Start only the Control Manager

cd /d "%~dp0\..\.."
python -m src.launcher --service manager
