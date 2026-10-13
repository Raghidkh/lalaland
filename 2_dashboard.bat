@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m streamlit run dashboard.py --browser.gatherUsageStats false
