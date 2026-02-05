@echo off
REM Stop all MLS services

cd /d "%~dp0\..\.."

echo Stopping all MLS services...
python -m src.launcher --stop

echo.
pause
