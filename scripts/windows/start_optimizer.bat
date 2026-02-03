@echo off
REM Start only the Optimizer Flask Server

cd /d "%~dp0\..\.."
python -m src.launcher --service optimizer
