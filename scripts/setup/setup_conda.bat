@echo off
REM MLS Conda Environment Setup Script for Windows
REM Usage: setup_conda.bat [environment_name]

setlocal EnableDelayedExpansion

set ENV_NAME=%1
if "%ENV_NAME%"=="" set ENV_NAME=mls

echo ============================================
echo  MLS - Multi-Ion Lab System - Conda Setup
echo ============================================
echo  Environment Name: %ENV_NAME%
echo ============================================
echo.

REM Check if conda is available
where conda >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Conda not found!
    echo Please install Miniconda or Anaconda:
    echo https://docs.conda.io/en/latest/miniconda.html
    exit /b 1
)

conda --version
echo.

REM Check if environment.yml exists
if not exist environment.yml (
    echo ERROR: environment.yml not found in current directory
    exit /b 1
)

REM Check if environment already exists
echo Checking for existing environment...
conda env list | findstr "^%ENV_NAME% " >nul
if %ERRORLEVEL% EQU 0 (
    echo Environment '%ENV_NAME%' already exists
    set /p UPDATE="Do you want to update it? (y/n): "
    if /I "!UPDATE!"=="y" (
        echo Updating environment...
        call conda env update -f environment.yml -n %ENV_NAME% --prune
    ) else (
        echo Skipping environment creation
        goto :vscode_setup
    )
) else (
    echo Creating new environment '%ENV_NAME%'...
    call conda env create -f environment.yml -n %ENV_NAME%
)

if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Environment creation may have had issues
)

:vscode_setup
echo.
echo ============================================
echo  Setting up VS Code Configuration
echo ============================================

REM Get the conda environment path
for /f "tokens=*" %%a in ('conda run -n %ENV_NAME% python -c "import sys; print(sys.executable)" 2^>^&1') do (
    set PYTHON_PATH=%%a
)

echo Python path: %PYTHON_PATH%

REM Create .vscode directory if it doesn't exist
if not exist .vscode mkdir .vscode

REM Update VS Code settings with the correct Python path
REM Note: This is a simplified version - the Python script does a better job

echo.
echo ============================================
echo  Verification
echo ============================================

call conda run -n %ENV_NAME% python -c "
import sys
print(f'Python: {sys.executable}')
print(f'Version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')

packages = ['flask', 'zmq', 'numpy', 'cv2', 'yaml', 'scipy']
for pkg in packages:
    try:
        __import__(pkg)
        print(f'OK: {pkg}')
    except ImportError as e:
        print(f'FAIL: {pkg} - {e}')
"

if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Verification had issues
)

:done
echo.
echo ============================================
echo  Setup Complete!
echo ============================================
echo.
echo Next steps:
echo 1. Activate the environment:
echo    conda activate %ENV_NAME%
echo.
echo 2. Start the MLS services:
echo    python launcher.py
echo.
echo 3. Access the dashboard:
echo    http://localhost:5000
echo.
echo 4. In VS Code:
echo    - Press Ctrl+Shift+P
echo    - Type 'Python: Select Interpreter'
echo    - Choose '%ENV_NAME%' environment
echo.

pause
