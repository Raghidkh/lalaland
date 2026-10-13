@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe scrape.py
echo.
echo Opening the Excel report...
start "" "output\Adma_Real_Estate.xlsx"
pause
