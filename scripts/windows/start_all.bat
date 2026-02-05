@echo off
REM MLS Unified Launcher - Start All Services
REM Services: Manager, Camera, Flask Dashboard, Applet, Optimizer

cd /d "%~dp0\..\.."

echo ============================================
echo MLS Unified Launcher
echo ============================================
echo.
echo Starting all services:
echo   - Control Manager (ZMQ)   :5557
echo   - Camera Server (TCP)     :5558
echo   - Flask Dashboard (HTTP)  :5000
echo   - Applet Server (HTTP)    :5051
echo   - Optimizer Server (HTTP) :5050
echo.
echo Press Ctrl+C to stop all services
echo ============================================
echo.

python -m src.launcher --service all

if errorlevel 1 (
    echo.
    echo ERROR: Failed to start services
    pause
    exit /b 1
)

echo.
echo All services stopped.
pause
