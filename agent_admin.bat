@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

REM ============================================================
REM WinRemote Agent V1.0.0 - Windows 本机服务管理工具
REM 用法：右键「以管理员身份运行」，按菜单选择操作
REM ============================================================

title WinRemote Agent V1.0.0——服务管理

:menu
cls
echo.
echo ╔══════════════════════════════════════════╗
echo ║   WinRemote Agent V1.0.0 服务管理工具      ║
echo ╚══════════════════════════════════════════╝
echo.

REM 检查服务状态
nssm status WinRemoteAgent >nul 2>&1
if errorlevel 1 (
    echo  📊 当前状态: 服务未安装
) else (
    for /f "tokens=*" %%a in ('nssm status WinRemoteAgent 2^>nul') do echo  📊 当前状态: %%a
)

echo.
echo  ┌──────────────────────────────────────────┐
echo  │  [1] 启动 Agent      [2] 停止 Agent     │
echo  │  [3] 重启 Agent      [4] 查看状态      │
echo  │  [5] 安装服务        [6] 卸载服务      │
echo  │  [7] 查看日志        [8] 编辑配置      │
echo  │  [9] 查看实时输出    [0] 退出          │
echo  └──────────────────────────────────────────┘
echo.

set "choice="
set /p "choice=请选择操作 [0-9]: "

if "%choice%"=="" goto menu
if "%choice%"=="0" goto :exit
if "%choice%"=="1" goto :start
if "%choice%"=="2" goto :stop
if "%choice%"=="3" goto :restart
if "%choice%"=="4" goto :status
if "%choice%"=="5" goto :install
if "%choice%"=="6" goto :uninstall
if "%choice%"=="7" goto :logs
if "%choice%"=="8" goto :config
if "%choice%"=="9" goto :tail
goto menu

:start
echo.
echo ▶ 正在启动 WinRemoteAgent...
nssm start WinRemoteAgent 2>nul
if errorlevel 1 (
    echo ⚠️ 启动失败，可能服务未安装。请先选 [5] 安装。
) else (
    echo ✅ 启动命令已发送
    timeout /t 2 /nobreak >nul
    nssm status WinRemoteAgent
)
echo.
pause
goto menu

:stop
echo.
echo ⏹️ 正在停止 WinRemoteAgent...
nssm stop WinRemoteAgent 2>nul
if errorlevel 1 (
    echo ⚠️ 停止失败，可能服务未安装或未运行。
) else (
    echo ✅ 停止命令已发送
    timeout /t 2 /nobreak >nul
    nssm status WinRemoteAgent
)
echo.
pause
goto menu

:restart
echo.
echo 🔄 正在重启 WinRemoteAgent...
nssm restart WinRemoteAgent 2>nul
if errorlevel 1 (
    echo ⚠️ 重启失败，可能服务未安装。请先选 [5] 安装。
) else (
    echo ✅ 重启命令已发送
    timeout /t 3 /nobreak >nul
    nssm status WinRemoteAgent
)
echo.
pause
goto menu

:status
echo.
echo 📊 服务详细信息：
echo ──────────────────────────────────────────────
nssm status WinRemoteAgent 2>nul || echo 服务未安装
echo.
echo ── 配置摘要 ──────────────────────────────────
nssm get WinRemoteAgent Application 2>nul || echo 无
nssm get WinRemoteAgent AppDirectory 2>nul || echo 无
echo.
pause
goto menu

:install
echo.
echo ╔══════════════════════════════════════════╗
echo ║  安装 WinRemoteAgent 系统服务             ║
echo ╚══════════════════════════════════════════╝
echo.

REM 检查 nssm 是否可用
where nssm >nul 2>&1
if errorlevel 1 (
    echo ⚠️ 未找到 nssm.exe
    echo    请先将 nssm.exe 放入 C:\Windows\System32\ 或当前目录
    echo    下载地址：https://nssm.cc/release/nssm-2.24.zip
    echo    解压后复制 win64\nssm.exe 到 C:\Windows\
    pause
    goto menu
)

REM 定位 agent 目录和脚本
set "AGENT_DIR=%~dp0"
if not exist "%AGENT_DIR%winremote_agent.py" (
    echo ⚠️ 未找到 winremote_agent.py
    echo    请确保此 bat 与 winremote_agent.py 在同一目录
    echo    当前目录：%AGENT_DIR%
    pause
    goto menu
)

REM 检查是否已安装
nssm status WinRemoteAgent >nul 2>&1
if not errorlevel 1 (
    echo ⚠️ 服务已存在，请先卸载（选 [6]）再重新安装
    pause
    goto menu
)

REM 检查 run_agent.bat 是否存在
set "RUN_SCRIPT=%AGENT_DIR%run_agent.bat"
if not exist "%RUN_SCRIPT%" (
    echo ⚠️ 未找到 run_agent.bat 启动脚本
    echo    请先运行 install_agent.bat 进行交互式部署
    echo.
    echo    或者现在手动创建？[Y/n]
    set /p "CREATE_NOW="
    if /i "!CREATE_NOW!"=="n" goto menu

    echo.
    echo   ══ 快速创建 run_agent.bat ══
    set "SERVER_URL="
    set "TOKEN="
    set "AGENT_ID="

    set /p "SERVER_URL=请输入服务器 WebSocket 地址 [默认: ws://127.0.0.1:1024/w]: "
    if "!SERVER_URL!"=="" set SERVER_URL=ws://127.0.0.1:1024/w

    :admin_input_token
    set /p "TOKEN=请输入共享 Token: "
    if "!TOKEN!"=="" (
        echo   ❌ Token 不能为空！
        goto admin_input_token
    )
    if "!TOKEN!"=="change-me" (
        echo   ❌ 不能使用默认值！
        goto admin_input_token
    )
    if "!TOKEN!"=="请换成你的长随机Token" (
        echo   ❌ 不能使用占位文本！
        goto admin_input_token
    )

    set /p "AGENT_ID=请输入 Agent 名称 [默认: my-pc-001]: "
    if "!AGENT_ID!"=="" set AGENT_ID=my-pc-001

    echo @echo off > "%RUN_SCRIPT%"
    echo chcp 65001 ^>nul >> "%RUN_SCRIPT%"
    echo title WinRemote Agent V1.0.0 -- !AGENT_ID! >> "%RUN_SCRIPT%"
    echo cd /d "%AGENT_DIR%" >> "%RUN_SCRIPT%"
    echo python winremote_agent.py --server !SERVER_URL! --token !TOKEN! --agent-id !AGENT_ID! >> "%RUN_SCRIPT%"

    echo   ✅ run_agent.bat 已创建
)

echo.
echo 📦 正在注册 Windows 服务...
nssm install WinRemoteAgent "%RUN_SCRIPT%" || goto :install_fail
nssm set WinRemoteAgent AppDirectory "%AGENT_DIR%" || goto :install_fail
nssm set WinRemoteAgent DisplayName "WinRemote Agent V1.0.0" || goto :install_fail
nssm set WinRemoteAgent Description "AstrBot WinRemote Windows Agent V1.0.0" || goto :install_fail
nssm set WinRemoteAgent Start SERVICE_AUTO_START || goto :install_fail
nssm set WinRemoteAgent AppRestartDelay 5000 || goto :install_fail
nssm set WinRemoteAgent AppStdout "%AGENT_DIR%agent_stdout.log" || goto :install_fail
nssm set WinRemoteAgent AppStderr "%AGENT_DIR%agent_stderr.log" || goto :install_fail
nssm set WinRemoteAgent AppRotateFiles 1 || goto :install_fail
nssm set WinRemoteAgent AppRotateBytes 1048576 || goto :install_fail

echo.
echo ✅ 服务注册成功！
echo.
echo ┌──────────────────────────────────────────────┐
echo │  Agent 目录 : %AGENT_DIR%                     │
echo │  启动脚本   : %RUN_SCRIPT%                    │
echo └──────────────────────────────────────────────┘
echo.
echo 是否立即启动服务？[Y/n]
set "ans="
set /p "ans="
if /i "!ans!"=="n" goto menu
nssm start WinRemoteAgent
timeout /t 2 /nobreak >nul
nssm status WinRemoteAgent
echo.
pause
goto menu

:install_fail
echo.
echo ❌ 服务注册失败！
echo    · 请确认以管理员身份运行
echo    · nssm.exe 是否可用：where nssm
echo    · run_agent.bat 是否有效：type "%RUN_SCRIPT%"
pause
goto menu

:uninstall
echo.
echo ⚠️ 确认卸载 WinRemoteAgent 服务？[y/N]
set "ans="
set /p "ans="
if /i not "!ans!"=="y" (
    echo 已取消
    pause
    goto menu
)
echo.
echo 🗑️ 正在卸载服务...
nssm stop WinRemoteAgent 2>nul
timeout /t 1 /nobreak >nul
nssm remove WinRemoteAgent confirm 2>nul
if errorlevel 1 (
    echo ⚠️ 卸载可能未完全成功，请检查
) else (
    echo ✅ 服务已卸载
    echo.
    echo 是否删除启动脚本 run_agent.bat？[y/N]
    set "ans="
    set /p "ans="
    if /i "!ans!"=="y" (
        del /f /q "%AGENT_DIR%run_agent.bat" 2>nul
        echo ✅ 启动脚本已删除
    )
)
echo.
pause
goto menu

:logs
echo.
echo 📋 Agent 日志文件:
echo ──────────────────────────────────────────────
set "AGENT_DIR=%~dp0"
if exist "%AGENT_DIR%agent_stdout.log" (
    echo.
    echo ── stdout（最近 30 行）──
    powershell -Command "Get-Content '%AGENT_DIR%agent_stdout.log' -Tail 30"
) else (
    echo    agent_stdout.log 不存在
)
echo.
if exist "%AGENT_DIR%agent_stderr.log" (
    echo ── stderr（最近 30 行）──
    powershell -Command "Get-Content '%AGENT_DIR%agent_stderr.log' -Tail 30"
) else (
    echo    agent_stderr.log 不存在
)
echo.
pause
goto menu

:config
echo.
echo ⚙️ 编辑 Agent 配置
echo ──────────────────────────────────────────────
set "AGENT_DIR=%~dp0"
set "RUN_SCRIPT=%AGENT_DIR%run_agent.bat"
if exist "%RUN_SCRIPT%" (
    echo 正在打开: %RUN_SCRIPT%
    notepad "%RUN_SCRIPT%"
    echo.
    echo ⚠️ 修改配置后请重启服务（选 [3]）使更改生效
) else (
    echo ⚠️ 未找到 run_agent.bat，请先安装服务（选 [5]）
)
echo.
pause
goto menu

:tail
echo.
echo 📡 实时日志（按 Ctrl+C 退出）
echo ──────────────────────────────────────────────
set "AGENT_DIR=%~dp0"
if exist "%AGENT_DIR%agent_stdout.log" (
    powershell -Command "Get-Content '%AGENT_DIR%agent_stdout.log' -Wait -Tail 10"
) else (
    echo ⚠️ 日志文件不存在，Agent 可能未启动
    pause
)
goto menu

:exit
echo.
echo 再见！
timeout /t 1 /nobreak >nul
endlocal
exit /b 0