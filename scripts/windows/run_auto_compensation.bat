@echo off
REM Run Auto Compensation Experiment
REM Usage: run_auto_compensation.bat [options]

cd /d "%~dp0\..\.."
python -m src.applet.auto_compensation %*
