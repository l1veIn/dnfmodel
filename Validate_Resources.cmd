@echo off
cd /d "%~dp0"
"C:\ProgramData\miniconda3\python.exe" scripts\dnf_resources.py validate
pause
