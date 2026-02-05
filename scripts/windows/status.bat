@echo off
REM Check status of all MLS services

cd /d "%~dp0\..\.."

python -m src.launcher --status

echo.
pause
