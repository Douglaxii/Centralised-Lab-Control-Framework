@echo off
REM ============================================================================
REM Data Directory Setup Script
REM Creates standardized directory structure at E:/Data
REM ============================================================================

echo.
echo  ╔═══════════════════════════════════════════════════════════════╗
echo  ║     Lab Data Directory Setup - E:/Data Standardization        ║
echo  ╚═══════════════════════════════════════════════════════════════╝
echo.

REM Check if E: drive exists
echo Checking E: drive...
if not exist "E:\" (
    echo [ERROR] E: drive not found!
    echo.
    echo Please ensure the E: drive is connected and accessible.
    echo If your data drive has a different letter, edit this script
    echo and replace "E:" with your drive letter.
    echo.
    pause
    exit /b 1
)

echo [OK] E: drive found
echo.

REM ============================================================================
REM Create Directory Structure
REM ============================================================================

echo Creating directory structure...
echo.

REM Root data directory
set "BASE=E:\Data"
if not exist "%BASE%" (
    mkdir "%BASE%"
    echo [Created] %BASE%
) else (
    echo [Exists]  %BASE%
)

REM Telemetry data (LabVIEW writes here)
call :create_dir "%BASE%\telemetry\wavemeter"
call :create_dir "%BASE%\telemetry\smile\pmt"
call :create_dir "%BASE%\telemetry\smile\pressure"
call :create_dir "%BASE%\telemetry\camera"

REM Camera data
call :create_dir "%BASE%\camera\raw_frames"
call :create_dir "%BASE%\camera\processed_frames"
call :create_dir "%BASE%\camera\dcimg"
call :create_dir "%BASE%\camera\settings"

REM Experiments
call :create_dir "%BASE%\experiments"

REM Analysis
call :create_dir "%BASE%\analysis\results"
call :create_dir "%BASE%\analysis\settings"

REM Logs
call :create_dir "%BASE%\logs"

REM Debug
call :create_dir "%BASE%\debug"

REM Backup
call :create_dir "%BASE%\backup"

echo.
echo ═══════════════════════════════════════════════════════════════
echo  Directory Structure Complete!
echo ═══════════════════════════════════════════════════════════════
echo.

REM ============================================================================
REM Create README in data directory
REM ============================================================================

echo Creating README files...

echo # E:/Data Directory Structure > "%BASE%\README.txt"
echo. >> "%BASE%\README.txt"
echo This is the standardized data directory for the Lab Control Framework. >> "%BASE%\README.txt"
echo. >> "%BASE%\README.txt"
echo ## Directory Structure >> "%BASE%\README.txt"
echo. >> "%BASE%\README.txt"
echo ``` >> "%BASE%\README.txt"
echo E:/Data/ >> "%BASE%\README.txt"
echo ├── telemetry/              # Real-time telemetry data (LabVIEW writes here) >> "%BASE%\README.txt"
echo │   ├── wavemeter/          # Laser frequency data (*.dat) >> "%BASE%\README.txt"
echo │   ├── smile/ >> "%BASE%\README.txt"
echo │   │   ├── pmt/            # PMT counts (*.dat) >> "%BASE%\README.txt"
echo │   │   └── pressure/       # Vacuum pressure (*.dat) >> "%BASE%\README.txt"
echo │   └── camera/             # Camera position data (*.json) >> "%BASE%\README.txt"
echo │ >> "%BASE%\README.txt"
echo ├── camera/                 # Camera data >> "%BASE%\README.txt"
echo │   ├── raw_frames/         # Raw JPG frames from camera >> "%BASE%\README.txt"
echo │   ├── processed_frames/   # Annotated/processed frames for web UI >> "%BASE%\README.txt"
echo │   ├── dcimg/              # DCIMG recordings >> "%BASE%\README.txt"
echo │   └── settings/           # Camera configuration files >> "%BASE%\README.txt"
echo │ >> "%BASE%\README.txt"
echo ├── experiments/            # Experiment metadata and results >> "%BASE%\README.txt"
echo │ >> "%BASE%\README.txt"
echo ├── analysis/               # Analysis outputs >> "%BASE%\README.txt"
echo │   ├── results/            # Analysis results >> "%BASE%\README.txt"
echo │   └── settings/           # Analysis configuration >> "%BASE%\README.txt"
echo │ >> "%BASE%\README.txt"
echo ├── logs/                   # Application logs >> "%BASE%\README.txt"
echo │ >> "%BASE%\README.txt"
echo ├── debug/                  # Debug output >> "%BASE%\README.txt"
echo │ >> "%BASE%\README.txt"
echo └── backup/                 # Data backups >> "%BASE%\README.txt"
echo ``` >> "%BASE%\README.txt"

echo [Created] %BASE%\README.txt

REM ============================================================================
REM Summary
REM ============================================================================

echo.
echo ═══════════════════════════════════════════════════════════════
echo  Next Steps
echo ═══════════════════════════════════════════════════════════════
echo.
echo 1. Update LabVIEW VIs to write telemetry data to:
echo    E:\Data\telemetry\[wavemeter/smile]/
echo.
echo 2. Verify MLS\config\settings.yaml has output_base set to:
echo    E:/Data
echo.
echo 3. Restart the lab servers to use the new paths
echo.
echo 4. Access your data at: E:\Data\
echo.
echo ═══════════════════════════════════════════════════════════════
echo.
pause
goto :eof

REM ============================================================================
REM Helper function to create directory
REM ============================================================================
:create_dir
if not exist "%~1" (
    mkdir "%~1" 2>nul
    if exist "%~1" (
        echo [Created] %~1
    ) else (
        echo [ERROR] Failed to create: %~1
    )
) else (
    echo [Exists]  %~1
)
goto :eof
