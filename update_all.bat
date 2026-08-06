@echo off
REM ---------------------------------------------------------------
REM update_all.bat — full daily NSE update, one shot.
REM   1) run_daily.py   fetch all datasets + compute stats (into nse.db)
REM   2) export_db.py   rebuild the per-stock database\ folder tree
REM Used by Task Scheduler (task "NSE Daily Update"). Double-click to run
REM manually too. All output also goes to run_daily.log.
REM ---------------------------------------------------------------
cd /d "%~dp0"
echo ==== %DATE% %TIME%  update_all START ====
python run_daily.py
python export_db.py
echo ==== %DATE% %TIME%  update_all DONE ====
