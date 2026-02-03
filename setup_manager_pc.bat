@echo off
REM Setup script for Manager PC (134.99.120.40)
REM Ensures data directories exist at E:/data

echo ===========================================
echo MLS Manager PC Setup
echo ===========================================
echo.

REM Check if conda is available
where conda >nul 2>&1
if %errorlevel% neq 0 (
    echo Warning: conda not found in PATH
    echo Make sure to run this from an Anaconda Prompt
    echo.
)

REM Run Python setup script
if exist "setup_manager_pc.py" (
    python setup_manager_pc.py
) else (
    echo Error: setup_manager_pc.py not found
    exit /b 1
)

echo.
pause
