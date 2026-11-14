@echo off
REM ========================================================
REM  CLEBUGGER Daily GitHub Issue Synchronizer
REM ========================================================
setlocal
set PYTHON_EXE="C:\Program Files\CLE\python_runtime\python.exe"
if not exist %PYTHON_EXE% (
    set PYTHON_EXE=python
)

echo [%DATE% %TIME%] Starting daily GitHub issue sync for JRFK...
%PYTHON_EXE% "%~dp0bug.py" sync-github JRFK

echo [%DATE% %TIME%] Sync complete.
exit /b 0
