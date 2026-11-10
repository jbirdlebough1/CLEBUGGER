@echo off
title CLEBUGGER Launcher
cd /d "D:\CLEBUGGER"

echo ========================================================
echo   CLEBUGGER - Multi-Project Bug & Regression Tracker
echo ========================================================

:: Check if port 8999 is already listening
netstat -ano | findstr :8999 | findstr LISTENING >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] CLEBUGGER server is already running on port 8999.
) else (
    echo [*] Starting CLEBUGGER server in background on port 8999...
    start /b python server.py 8999 > server.log 2>&1
    timeout /t 1 /nobreak >nul
)

echo [*] Opening CLEBUGGER dashboard in Google Chrome...
start chrome "http://127.0.0.1:8999/" || start "" "http://127.0.0.1:8999/"
echo [*] CLEBUGGER is ready at http://127.0.0.1:8999/
