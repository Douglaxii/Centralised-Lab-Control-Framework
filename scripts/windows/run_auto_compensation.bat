@echo off
REM One-line command to run Auto Compensation Experiment
REM Usage: run_auto_compensation.bat [options]

cd /d "%~dp0"
python server\applet\run_auto_comp.py %*
