@echo off
REM Start the Applet Flask Server
REM Usage: start_applet_server.bat [options]

cd /d "%~dp0"
python server\applet\launcher.py %*
