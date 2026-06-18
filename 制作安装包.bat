@echo off
chcp 65001 >nul
REM ============================================================
REM   一键：打包 exe + 编译成正式安装包(Setup.exe)
REM   双击本文件即可。最终安装包输出到桌面：
REM     量化终端_安装程序_v1.0.exe
REM ============================================================
cd /d "%~dp0"

set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
  echo [错误] 找不到虚拟环境 .venv,请先建好 .venv 并装好依赖。
  pause & exit /b 1
)

echo [1/3] 确认打包工具...
"%PY%" -m pip install --disable-pip-version-check -q pyinstaller

echo.
echo [2/3] 打包成独立程序(几分钟,勿关窗口)...
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
if not exist "dist\量化终端\量化终端.exe" (
  echo [失败] 打包没成功,中止。
  pause & exit /b 1
)

echo.
echo [3/3] 编译安装包...
REM 自动找 ISCC.exe(Inno Setup 编译器)
set ISCC=
for %%P in (
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  "C:\Program Files\Inno Setup 6\ISCC.exe"
) do if exist %%P set ISCC=%%P

if "%ISCC%"=="" (
  echo [错误] 没找到 Inno Setup 编译器 ISCC.exe。
  echo 请先安装 Inno Setup:  winget install -e --id JRSoftware.InnoSetup
  pause & exit /b 1
)

"%ISCC%" installer.iss
echo.
if exist "D:\桌面\量化终端_安装程序_v1.0.exe" (
  echo [完成] 安装包已生成到桌面: D:\桌面\量化终端_安装程序_v1.0.exe
) else (
  echo [提示] 已编译,安装包输出在 installer.iss 里 OutputDir 指定的目录(D:\桌面)。
)
echo.
pause
