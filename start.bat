@echo off
title JARVIS Launcher
cd /d "%~dp0"

echo Starting JARVIS...

REM Use pythonw to run launcher with NO console window
start "" pythonw launcher.pyw

echo JARVIS is starting in the background.
echo You can close this window.
timeout /t 2 /nobreak >nul
exit