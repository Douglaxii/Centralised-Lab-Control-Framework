@echo off
echo Starting MLS Control Manager...
cd /d "%~dp0\..\.."
python -m src.server.manager.manager
