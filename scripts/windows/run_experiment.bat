@echo off
REM Run any applet experiment
REM Usage: run_experiment.bat [experiment_name] [options]
REM Example: run_experiment.bat auto_compensation

cd /d "%~dp0\..\.."
python -m src.applet.run_%1 %*
