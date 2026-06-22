@echo off
REM Quick launcher for GHOST text-only mode
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python ghost.py
pause
