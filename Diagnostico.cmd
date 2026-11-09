@echo off
rem Diagnóstico de dependencias y configuración.
cd /d "%~dp0backend"
"%~dp0.venv\Scripts\python.exe" -m jarvis doctor
pause
