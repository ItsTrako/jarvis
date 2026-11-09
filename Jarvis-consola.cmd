@echo off
rem J.A.R.V.I.S. en modo consola (muestra los registros en directo).
cd /d "%~dp0backend"
"%~dp0.venv\Scripts\python.exe" -m jarvis run
pause
