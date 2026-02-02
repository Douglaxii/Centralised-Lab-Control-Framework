@echo off
REM One-line command to run Trap Eigenmode Experiment
REM Usage: run_trap_eigenmode.bat -u 200 -e1 10 -e2 10 -m 9 3

cd /d "%~dp0"
python server\applet\run_trap_eigenmode.py %*
