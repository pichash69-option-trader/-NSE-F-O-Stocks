@echo off
REM ---------------------------------------------------------------
REM run_daily.bat — runs the NSE daily update. Used by Task Scheduler.
REM Double-click to run manually, or point Task Scheduler at this file.
REM ---------------------------------------------------------------
cd /d "%~dp0"
REM Uses "python" from your system PATH. If python isn't on PATH, replace with
REM the full path to python.exe, e.g. "C:\Path\To\Python311\python.exe".
python run_daily.py
