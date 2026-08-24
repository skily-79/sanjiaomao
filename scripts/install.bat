@echo off
cd /d "%~dp0"
echo Running local installer...
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
pause
