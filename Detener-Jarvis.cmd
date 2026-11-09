@echo off
rem Detiene J.A.R.V.I.S. de forma ordenada.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
