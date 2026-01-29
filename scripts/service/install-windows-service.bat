@echo off
REM Install Lab Control as Windows Service using NSSM
REM Requires NSSM: https://nssm.cc/download

echo ==========================================
echo Installing Lab Control Windows Service
echo ==========================================

set "NSSM=nssm"
set "SERVICE_NAME=LabControl"
set "INSTALL_DIR=%~dp0.."

REM Check if NSSM is available
where %NSSM% >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: NSSM not found in PATH
    echo Please download from https://nssm.cc/download
    echo and add to PATH
    exit /b 1
)

REM Remove existing service if present
sc query %SERVICE_NAME% >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Stopping existing service...
    net stop %SERVICE_NAME% >nul 2>&1
    %NSSM% remove %SERVICE_NAME% confirm >nul 2>&1
)

echo Installing service...
%NSSM% install %SERVICE_NAME% python "%INSTALL_DIR%\launcher.py"
%NSSM% set %SERVICE_NAME% AppDirectory "%INSTALL_DIR%"
%NSSM% set %SERVICE_NAME% AppParameters --daemon
%NSSM% set %SERVICE_NAME% DisplayName "Lab Control System"
%NSSM% set %SERVICE_NAME% Description "Manages Camera, Manager, and Flask services"
%NSSM% set %SERVICE_NAME% Start SERVICE_AUTO_START

REM Log configuration
%NSSM% set %SERVICE_NAME% AppStdout "%INSTALL_DIR%\logs\service.log"
%NSSM% set %SERVICE_NAME% AppStderr "%INSTALL_DIR%\logs\service.log"
%NSSM% set %SERVICE_NAME% AppRotateFiles 1
%NSSM% set %SERVICE_NAME% AppRotateBytes 10485760

REM Restart configuration
%NSSM% set %SERVICE_NAME% AppRestartDelay 10000
%NSSM% set %SERVICE_NAME% AppThrottle 5000

echo Starting service...
net start %SERVICE_NAME%

echo.
echo ==========================================
echo Installation complete!
echo Service: %SERVICE_NAME%
echo Status: sc query %SERVICE_NAME%
echo Logs: %INSTALL_DIR%\logs\
echo ==========================================
