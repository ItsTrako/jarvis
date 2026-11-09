@echo off
rem Inicia J.A.R.V.I.S. en segundo plano (icono en la bandeja) y abre la interfaz.
cd /d "%~dp0backend"
start "" "%~dp0.venv\Scripts\pythonw.exe" -m jarvis run --tray
