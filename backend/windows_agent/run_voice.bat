@echo off
REM Quick launcher for GHOST voice mode (assumes setup.bat was run once)
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python voice_ghost.py
pause
