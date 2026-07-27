@echo off
REM ---------------------------------------------------------------
REM run_dashboard.bat — double-click to open the dashboard.
REM Opens http://localhost:8501 in your browser.
REM ---------------------------------------------------------------
cd /d "%~dp0"
echo Starting NSE dashboard...
echo Browser me khulega: http://localhost:8501
echo Band karne ke liye is window me Ctrl+C dabao.
streamlit run dashboard.py
pause
