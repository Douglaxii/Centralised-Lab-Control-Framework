@echo off
echo Usage: run_experiment.bat ^<experiment_name^>
if "%~1"=="" (
    echo Please provide an experiment name
    exit /b 1
)
cd /d "%~dp0\..\.."
python -m src.applet.run_%1
