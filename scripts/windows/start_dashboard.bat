@echo off
REM Start only the Dashboard Flask Server

cd /d "%~dp0\..\.."
python -m src.launcher --service flask
