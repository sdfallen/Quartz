@echo off
title JARVIS Stopper
echo Stopping JARVIS...

REM Kill the python processes running our scripts
taskkill /F /FI "WINDOWTITLE eq JARVIS Backend" >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1

echo JARVIS stopped.
timeout /t 2 /nobreak >nul
exit