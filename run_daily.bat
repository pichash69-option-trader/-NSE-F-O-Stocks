@echo off
REM ---------------------------------------------------------------
REM run_daily.bat — runs the NSE daily update. Used by Task Scheduler.
REM Double-click to run manually, or point Task Scheduler at this file.
REM ---------------------------------------------------------------
cd /d "%~dp0"
"C:\Users\ajayk\AppData\Local\Programs\Python\Python311\python.exe" run_daily.py
