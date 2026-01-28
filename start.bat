@echo off
REM Start Lab Control System (Windows)
REM Usage: start.bat [interactive|daemon|status|stop]

set MODE=%1
if "%MODE%"=="" set MODE=interactive

cd /d "%~dp0"

echo ==========================================
echo Lab Control System - Starting in %MODE% mode
echo ==========================================

if "%MODE%"=="interactive" (
    python launcher.py --interactive
) else if "%MODE%"=="daemon" (
    python launcher.py --daemon
    echo Started in background. Check logs\launcher.log for status.
) else if "%MODE%"=="status" (
    python launcher.py --status
) else if "%MODE%"=="stop" (
    python launcher.py --stop
) else if "%MODE%"=="restart" (
    python launcher.py --restart
) else (
    echo Usage: start.bat [interactive^|daemon^|status^|stop^|restart]
    echo.
    echo   interactive  - Start with interactive console (default)
    echo   daemon       - Start in background
    echo   status       - Show service status
    echo   stop         - Stop all services
    echo   restart      - Restart all services
)
