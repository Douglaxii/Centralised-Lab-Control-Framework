@echo off
REM Start all services EXCEPT camera
REM Useful when camera hardware is not available

cd /d "%~dp0\..\.."

echo ============================================
echo MLS Launcher (without Camera)
echo ============================================
echo.
echo Starting services:
echo   - Control Manager (ZMQ)   :5557
echo   - Flask Dashboard (HTTP)  :5000
echo   - Applet Server (HTTP)    :5051
echo   - Optimizer Server (HTTP) :5050
echo.
echo Camera service is NOT started
echo ============================================
echo.

REM Start services individually without camera
start "Manager" python -m src.launcher --service manager --daemon
 timeout /t 2 /nobreak >nul

start "Flask" python -m src.launcher --service flask --daemon
 timeout /t 2 /nobreak >nul

start "Applet" python -m src.launcher --service applet --daemon
 timeout /t 2 /nobreak >nul

start "Optimizer" python -m src.launcher --service optimizer --daemon

echo Services started in separate windows.
echo Use 'python -m src.launcher --status' to check status
echo Use 'python -m src.launcher --stop' to stop all
echo.
pause
