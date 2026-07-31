@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM WinRemote Agent V0.4 - Windows 一键部署脚本
REM 用法：右键「以管理员身份运行」
REM ============================================================

REM ===== 用户需编辑的 3 个变量 =====
set SERVER_URL=ws://127.0.0.1:6190/winremote
set TOKEN=请换成你的长随机Token
set AGENT_ID=my-pc-001
REM ============================================================

echo [1/5] 正在安装 Python 依赖...
pip install websocket-client pillow pyautogui 2>nul
if errorlevel 1 (
    echo ⚠️ pip 安装失败，请确认 Python 已加入 PATH
    pause
    exit /b 1
)
echo ✅ 依赖安装完成

echo.
echo [2/5] 下载 NSSM（将 Agent 注册为 Windows 服务）...
set NSSM_URL=https://nssm.cc/release/nssm-2.24.zip
set NSSM_ZIP=%TEMP%\nssm.zip
set NSSM_DIR=C:\nssm
powershell -Command "(New-Object Net.WebClient).DownloadFile('%NSSM_URL%','%NSSM_ZIP%')" 2>nul
if exist "%NSSM_ZIP%" (
    powershell -Command "Expand-Archive -Path '%NSSM_ZIP%' -DestinationPath '%NSSM_DIR%' -Force"
    copy /Y "%NSSM_DIR%\nssm-2.24\win64\nssm.exe" "C:\Windows\System32\" >nul 2>&1
    echo ✅ NSSM 安装完成
) else (
    echo ⚠️ NSSM 下载失败（可手动下载放入 C:\Windows\System32\）
)

echo.
echo [3/5] 创建启动脚本...
set AGENT_DIR=%~dp0
set START_SCRIPT=%AGENT_DIR%run_agent.bat
echo @echo off > "%START_SCRIPT%"
echo cd /d "%AGENT_DIR%" >> "%START_SCRIPT%"
echo python winremote_agent.py --server %SERVER_URL% --token %TOKEN% --agent-id %AGENT_ID% >> "%START_SCRIPT%"
echo ✅ 启动脚本已创建: %START_SCRIPT%

echo.
echo [4/5] 注册为 Windows 服务（开机自启 + 崩溃自拉）...
nssm install WinRemoteAgent "%START_SCRIPT%" 2>nul
if errorlevel 1 (
    echo ⚠️ NSSM 未安装，跳过服务注册（可手动运行 run_agent.bat）
) else (
    nssm set WinRemoteAgent AppDirectory "%AGENT_DIR%" 2>nul
    nssm set WinRemoteAgent DisplayName "WinRemote Agent V0.4" 2>nul
    nssm set WinRemoteAgent Description "AstrBot WinRemote Windows Agent" 2>nul
    nssm set WinRemoteAgent Start SERVICE_AUTO_START 2>nul
    nssm set WinRemoteAgent AppRestartDelay 5000 2>nul
    nssm start WinRemoteAgent 2>nul
    echo ✅ 服务已注册并启动
)

echo.
echo [5/5] 部署完成！
echo.
echo ┌──────────────────────────────────────────────┐
echo │  Agent ID   : %AGENT_ID%                    │
echo │  Server URL : %SERVER_URL%                  │
echo │  Token      : %TOKEN%                      │
echo │  Agent 目录 : %AGENT_DIR%                   │
echo └──────────────────────────────────────────────┘
echo.
echo 管理命令：
echo   启动: nssm start WinRemoteAgent
echo   停止: nssm stop WinRemoteAgent
echo   重启: nssm restart WinRemoteAgent
echo   状态: nssm status WinRemoteAgent
echo   卸载: nssm remove WinRemoteAgent confirm
echo.
echo ⚠️ 提醒：正式使用请配合 SSH 隧道，不要裸奔公网！
echo     ssh -N -R 6190:localhost:6190 root@你的服务器IP
echo.
pause
endlocal
