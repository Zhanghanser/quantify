@echo off
chcp 65001 >nul
rem === Quantify desktop (native window, no console, no browser) ===
cd /d "%~dp0"
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0native_app.py"
exit
