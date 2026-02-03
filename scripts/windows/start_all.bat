@echo off
REM MLS Unified Launcher - Start all services
REM Usage: start_all.bat [options]
REM
echo ==========================================
echo MLS Lab Control System
echo ==========================================

cd /d "%~dp0\..\.."

if "%~1"=="" (
    echo Starting all services...
    echo.
    echo Services:
    echo   - Manager      (ZMQ)     Port 5557
    echo   - Dashboard    (Flask)   Port 5000  http://localhost:5000
    echo   - Applet       (Flask)   Port 5051  http://localhost:5051
    echo   - Optimizer    (Flask)   Port 5050  http://localhost:5050
    echo.
    python -m src.launcher
) else if "%~1"=="--help" (
    python -m src.launcher --help
) else (
    python -m src.launcher %*
)
