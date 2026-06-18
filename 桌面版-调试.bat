@echo off
chcp 65001 >nul
rem === Quantify desktop - DEBUG mode (keeps console to show errors) ===
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0native_app.py"
echo.
echo (program exited - press any key to close)
pause >nul
