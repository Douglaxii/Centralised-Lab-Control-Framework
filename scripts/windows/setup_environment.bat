@echo off
REM MLS Environment Setup Script
REM Automatically detects environment and configures paths

cd /d "%~dp0\..\.."

echo ============================================
echo MLS Environment Setup
echo ============================================
echo.

if "%1"=="--help" (
    echo Usage: setup_environment.bat [option]
    echo.
    echo Options:
    echo   --dev     Force development mode (laptop)
    echo   --prod    Force production mode (manager PC)
    echo   --check   Check current setup only
    echo   (none)    Auto-detect environment
    echo.
    echo Examples:
    echo   setup_environment.bat           Auto-detect and setup
    echo   setup_environment.bat --dev     Force development mode
    echo   setup_environment.bat --prod    Force production mode
    echo   setup_environment.bat --check   Validate current setup
    pause
    exit /b 0
)

set ARGS=
if "%1"=="--dev" set ARGS=--dev
if "%1"=="--development" set ARGS=--dev
if "%1"=="--prod" set ARGS=--prod
if "%1"=="--production" set ARGS=--prod
if "%1"=="--check" set ARGS=--check
if "%1"=="--validate" set ARGS=--check

python scripts\setup\auto_config.py %ARGS%

if errorlevel 1 (
    echo.
    echo ⚠️ Setup completed with warnings or errors
    pause
    exit /b 1
)

echo.
pause
