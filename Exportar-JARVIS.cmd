@echo off
rem Crea un paquete para instalar JARVIS exactamente igual en otro PC (incluye memoria y conversaciones).
cd /d "%~dp0backend"
"%~dp0.venv\Scripts\python.exe" -m jarvis export
if exist "%~dp0exportar" explorer "%~dp0exportar"
pause
