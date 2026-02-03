@echo off
REM Start only the Applet Flask Server

cd /d "%~dp0\..\.."
python -m src.launcher --service applet
