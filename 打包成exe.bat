@echo off
chcp 65001 >nul
REM ============================================================
REM   一键把项目打包成独立 exe(文件夹版,最稳妥)
REM   双击本文件即可。打包结果在  dist\量化终端\
REM ============================================================
cd /d "%~dp0"

set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
  echo [错误] 找不到虚拟环境 .venv,请先在项目里建好 .venv 并装好依赖。
  pause
  exit /b 1
)

echo 正在确认 PyInstaller 已安装...
"%PY%" -m pip install --disable-pip-version-check -q pyinstaller

echo.
echo 开始打包(几分钟,期间请勿关闭窗口)...
"%PY%" -m PyInstaller --noconfirm --clean --log-level WARN ^
  --name "量化终端" --icon icon.ico --version-file version_info.txt ^
  --add-data "web;web" ^
  --collect-all ccxt ^
  --collect-submodules uvicorn ^
  --collect-submodules src ^
  --hidden-import config --hidden-import run_web ^
  --exclude-module matplotlib --exclude-module streamlit ^
  --exclude-module plotly --exclude-module altair ^
  --exclude-module tkinter --exclude-module PyQt5 ^
  --exclude-module PySide2 --exclude-module PySide6 ^
  desktop_app.py

echo.
if exist "dist\量化终端\量化终端.exe" (
  echo [完成] 打包成功!
  echo 结果在:  %cd%\dist\量化终端\
  echo 把这【整个文件夹】拷到别的电脑,双击 量化终端.exe 即可运行。
) else (
  echo [失败] 没有生成 exe,请把上面的报错发给开发者排查。
)
echo.
pause
