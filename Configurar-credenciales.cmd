@echo off
rem Asistente de credenciales (API keys, token de Telegram, PIN).
cd /d "%~dp0backend"
"%~dp0.venv\Scripts\python.exe" -m jarvis setup
pause
