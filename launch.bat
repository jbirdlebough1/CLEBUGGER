@echo off
setlocal
title CLEBUGGER Launcher
cd /d "%~dp0"

echo ========================================================
echo   CLEBUGGER - Multi-Project Bug ^& Regression Tracker
echo ========================================================

:: Check if port 8999 is already listening
netstat -ano | findstr :8999 | findstr LISTENING >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] CLEBUGGER server is already running on port 8999.
    goto :open_browser
)

:: Resolve real Python 3 runtime (prefer bundled runtime, avoid Win11 Store alias)
set "PYTHONW_EXE="
set "PYTHON_EXE="
if exist "C:\Program Files\CLE\python_runtime\pythonw.exe" set "PYTHONW_EXE=C:\Program Files\CLE\python_runtime\pythonw.exe"
if exist "C:\Program Files\CLE\python_runtime\python.exe" set "PYTHON_EXE=C:\Program Files\CLE\python_runtime\python.exe"
if not defined PYTHON_EXE if exist "%~dp0..\MEAGCLE\python_runtime\pythonw.exe" set "PYTHONW_EXE=%~dp0..\MEAGCLE\python_runtime\pythonw.exe"
if not defined PYTHON_EXE if exist "%~dp0..\MEAGCLE\python_runtime\python.exe" set "PYTHON_EXE=%~dp0..\MEAGCLE\python_runtime\python.exe"
if not defined PYTHON_EXE (
    python -c "import sys" >nul 2>&1
    if %errorlevel% equ 0 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    py -3 -c "import sys" >nul 2>&1
    if %errorlevel% equ 0 set "PYTHON_EXE=py -3"
)

if defined PYTHONW_EXE (
    echo [*] Starting CLEBUGGER server in background on port 8999 using %PYTHONW_EXE%...
    start "CLEBUGGER" "%PYTHONW_EXE%" "%~dp0server.py" 8999
) else if defined PYTHON_EXE (
    echo [*] Starting CLEBUGGER server in background on port 8999 using %PYTHON_EXE%...
    start "CLEBUGGER" /b "%PYTHON_EXE%" "%~dp0server.py" 8999 > "%~dp0server.log" 2>&1
) else (
    echo [ERROR] Python 3 runtime not found in C:\Program Files\CLE\python_runtime\ or PATH.
    exit /b 1
)

:: Wait up to ~5 seconds for port 8999 to bind (ping avoids stdin redirect issue)
for /l %%i in (1,1,10) do (
    netstat -ano | findstr ":8999 " | findstr "LISTENING" >nul 2>&1 && goto :open_browser
    ping -n 2 127.0.0.1 >nul
)

netstat -ano | findstr ":8999 " | findstr "LISTENING" >nul 2>&1 && goto :open_browser
echo [ERROR] CLEBUGGER server failed to bind port 8999. See "%~dp0server.log":
if exist "%~dp0server.log" type "%~dp0server.log"
exit /b 1

:open_browser
if /i not "%~1"=="--no-browser" (
    echo [*] Opening CLEBUGGER dashboard in browser...
    start "" "http://127.0.0.1:8999/"
)
echo [*] CLEBUGGER is ready at http://127.0.0.1:8999/
endlocal
