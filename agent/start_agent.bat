@echo off
chcp 65001 >nul
echo ========================================
echo   WinRemote Agent 启动脚本
echo ========================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [信息] 检查依赖...
python -c "import pyautogui, PIL, requests" >nul 2>&1
if errorlevel 1 (
    echo [信息] 安装依赖...
    pip install pyautogui pillow requests
)

echo [信息] 启动 Agent...
python agent/winremote_agent.py

pause
