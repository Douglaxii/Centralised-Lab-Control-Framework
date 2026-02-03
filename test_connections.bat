@echo off
:: Manager PC Connection Test Wrapper
:: 
:: Usage:
::   test_connections.bat              - Run all tests
::   test_connections.bat --camera     - Test camera only
::   test_connections.bat --artiq      - Test ARTIQ only
::   test_connections.bat --labview    - Test LabVIEW only
::   test_connections.bat --verbose    - Detailed output
::

echo ============================================================
echo    Manager PC Connection Test Suite
echo ============================================================
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    exit /b 1
)

:: Run the test script with all arguments passed through
cd /d "%~dp0"
python test_connections.py %*

:: Pause if double-clicked (no arguments)
if "%~1"=="" (
    echo.
    pause
)
