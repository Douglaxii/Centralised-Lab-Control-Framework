@echo off
chcp 65001 >nul
REM ============================================================================
REM Lab Server Launcher - Simplified Startup Script
REM ============================================================================

echo.
echo  ╔═══════════════════════════════════════════════════════════════╗
echo  ║          Lab Control Framework - Server Launcher              ║
echo  ╚═══════════════════════════════════════════════════════════════╝
echo.

REM Configuration - adjust these paths to your setup
set MLS_PATH=D:\MLS
set MHI_CAM_PATH=D:\mhi_cam
set PYTHON_MLS=python
set PYTHON_MHI=C:\Users\Hamamatsu\Developer\GitHub\mhi_cam\.venv\Scripts\python.exe

REM Check if paths exist
if not exist "%MLS_PATH%" (
    echo [ERROR] MLS path not found: %MLS_PATH%
    echo Please edit this script and set the correct MLS_PATH
    pause
    exit /b 1
)

cd /d "%MLS_PATH%"

REM ============================================================================
REM Function to check if a port is already in use
REM ============================================================================
:check_port
set PORT=%1
set NAME=%2
netstat -an | findstr ":%PORT% " | findstr "LISTENING" >nul
if %errorLevel% == 0 (
    echo [WARNING] Port %PORT% is already in use - %NAME% may already be running
    exit /b 1
)
exit /b 0

REM ============================================================================
REM Menu
REM ============================================================================
:menu
echo.
echo  What would you like to start?
echo.
echo   [1] Start ALL servers (Camera + Manager + Flask UI + Legacy API)
echo   [2] Start Core servers only (Camera + Manager + Flask UI)
echo   [3] Start Camera Server only
echo   [4] Start Control Manager only
echo   [5] Start Flask Web UI only
echo   [6] Start Legacy Flask API only
echo   [7] STOP all servers
echo   [8] Check server status
echo   [Q] Quit
echo.
set /p choice="Enter your choice (1-8 or Q): "

if "%choice%"=="1" goto :start_all
if "%choice%"=="2" goto :start_core
if "%choice%"=="3" goto :start_camera
if "%choice%"=="4" goto :start_manager
if "%choice%"=="5" goto :start_flask_ui
if "%choice%"=="6" goto :start_legacy_api
if "%choice%"=="7" goto :stop_all
if "%choice%"=="8" goto :check_status
if /i "%choice%"=="Q" exit /b 0
goto :menu

REM ============================================================================
REM Start All Servers
REM ============================================================================
:start_all
call :start_camera
timeout /t 2 >nul
call :start_manager
timeout /t 2 >nul
call :start_flask_ui
timeout /t 2 >nul
call :start_legacy_api
goto :menu

REM ============================================================================
REM Start Core Servers (Recommended)
REM ============================================================================
:start_core
call :start_camera
timeout /t 2 >nul
call :start_manager
timeout /t 2 >nul
call :start_flask_ui
echo.
echo  ╔═══════════════════════════════════════════════════════════════╗
echo  ║  Core servers starting...                                     ║
echo  ║  • Access Web UI at: http://localhost:5001                    ║
echo  ╚═══════════════════════════════════════════════════════════════╝
goto :menu

REM ============================================================================
REM Start Camera Server
REM ============================================================================
:start_camera
call :check_port 5558 "Camera Server"
if %errorLevel% neq 0 goto :eof

echo.
echo [1/4] Starting Camera Server (Port 5558)...
start "Camera Server - Port 5558" cmd /k "cd /d %MLS_PATH% && %PYTHON_MLS% server\cam\camera_server_parallel.py"
echo [OK] Camera Server window opened
timeout /t 1 >nul
goto :eof

REM ============================================================================
REM Start Control Manager
REM ============================================================================
:start_manager
call :check_port 5557 "Control Manager"
if %errorLevel% neq 0 goto :eof

echo.
echo [2/4] Starting Control Manager (Port 5557)...
echo         This is the central coordinator for all lab components.
start "Control Manager - Port 5557" cmd /k "cd /d %MLS_PATH% && %PYTHON_MLS% server\communications\manager.py"
echo [OK] Control Manager window opened
timeout /t 1 >nul
goto :eof

REM ============================================================================
REM Start Flask Web UI (Modern)
REM ============================================================================
:start_flask_ui
call :check_port 5001 "Flask Web UI"
if %errorLevel% neq 0 goto :eof

echo.
echo [3/4] Starting Flask Web UI (Port 5001)...
echo         Access at: http://localhost:5001
echo         Features: Camera feed, Telemetry graphs, Control cockpit
cd /d "%MLS_PATH%"
start "Flask Web UI - Port 5001" cmd /k "cd /d %MLS_PATH% && %PYTHON_MLS% server\Flask\flask_server.py"
echo [OK] Flask Web UI window opened
timeout /t 1 >nul
goto :eof

REM ============================================================================
REM Start Legacy Flask API
REM ============================================================================
:start_legacy_api
call :check_port 5000 "Legacy Flask API"
if %errorLevel% neq 0 goto :eof

echo.
echo [4/4] Starting Legacy Flask API (Port 5000)...
echo         Access at: http://localhost:5000
echo         Features: DDS control, Camera settings, Analysis forms
cd /d "%MHI_CAM_PATH%\communication"
start "Legacy Flask API - Port 5000" cmd /k "cd /d %MHI_CAM_PATH%\communication && %PYTHON_MHI% flask_server_setup.py"
echo [OK] Legacy Flask API window opened
timeout /t 1 >nul
goto :eof

REM ============================================================================
REM Stop All Servers
REM ============================================================================
:stop_all
echo.
echo Stopping all servers...
echo.

echo [1] Stopping Legacy Flask API (Port 5000)...
if exist "%MHI_CAM_PATH%\communication\shutdown_server.py" (
    %PYTHON_MHI% "%MHI_CAM_PATH%\communication\shutdown_server.py" 2>nul
) else (
    taskkill /FI "WINDOWTITLE eq Legacy Flask API - Port 5000" /T /F 2>nul
)

echo [2] Stopping Flask Web UI (Port 5001)...
taskkill /FI "WINDOWTITLE eq Flask Web UI - Port 5001" /T /F 2>nul

echo [3] Stopping Control Manager (Port 5557)...
taskkill /FI "WINDOWTITLE eq Control Manager - Port 5557" /T /F 2>nul

echo [4] Stopping Camera Server (Port 5558)...
taskkill /FI "WINDOWTITLE eq Camera Server - Port 5558" /T /F 2>nul

echo.
echo [OK] All servers stopped
goto :menu

REM ============================================================================
REM Check Server Status
REM ============================================================================
:check_status
echo.
echo ═══════════════════════════════════════════════════════════════
echo  Server Status Check
echo ═══════════════════════════════════════════════════════════════
echo.
echo Checking ports...
echo.

echo Camera Server (Port 5558):
netstat -an | findstr ":5558 " | findstr "LISTENING" >nul
if %errorLevel% == 0 (
    echo   [RUNNING]
) else (
    echo   [STOPPED]
)

echo.
echo Control Manager (Port 5557):
netstat -an | findstr ":5557 " | findstr "LISTENING" >nul
if %errorLevel% == 0 (
    echo   [RUNNING]
) else (
    echo   [STOPPED]
)

echo.
echo Flask Web UI (Port 5001):
netstat -an | findstr ":5001 " | findstr "LISTENING" >nul
if %errorLevel% == 0 (
    echo   [RUNNING] - Access: http://localhost:5001
) else (
    echo   [STOPPED]
)

echo.
echo Legacy Flask API (Port 5000):
netstat -an | findstr ":5000 " | findstr "LISTENING" >nul
if %errorLevel% == 0 (
    echo   [RUNNING] - Access: http://localhost:5000
) else (
    echo   [STOPPED]
)

echo.
echo Press any key to continue...
pause >nul
goto :menu
