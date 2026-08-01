@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

REM ============================================================
REM WinRemote Agent V0.9.5 - Windows 交互式部署脚本
REM 用法：右键「以管理员身份运行」
REM V0.9.5 改动：删除自动下载 NSSM，改为交互式提示
REM ============================================================

echo ╔══════════════════════════════════════════╗
echo ║   WinRemote Agent V0.9.5 交互式安装向导   ║
echo ╚══════════════════════════════════════════╝
echo.

REM ===== 交互式收集配置 =====
set "SERVER_URL="
set "TOKEN="
set "AGENT_ID="

:input_server
set /p "SERVER_URL=请输入服务器 WebSocket 地址 [默认: ws://127.0.0.1:6190/winremote]: "
if "!SERVER_URL!"=="" set SERVER_URL=ws://127.0.0.1:6190/winremote

:input_token
echo.
echo ⚠️ Token 必须 ≥16 位随机字符！
echo    推荐生成方式: python -c "import secrets;print(secrets.token_hex(32))"
echo.
set /p "TOKEN=请输入共享 Token: "
if "!TOKEN!"=="" (
    echo ❌ Token 不能为空！
    goto input_token
)
if "!TOKEN!"=="change-me" (
    echo ❌ 不能使用默认值，请输入真实 Token！
    goto input_token
)

:input_agent_id
echo.
set /p "AGENT_ID=请输入 Agent ID [默认: my-pc-001]: "
if "!AGENT_ID!"=="" set AGENT_ID=my-pc-001

echo.
echo ┌──────────────────────────────────────────────┐
echo │ 配置确认：                                │
echo │   Server  : !SERVER_URL!                   │
echo │   Token   : [已输入，长度 !LEN!]          │
echo │   Agent ID: !AGENT_ID!                     │
echo └──────────────────────────────────────────────┘
echo.
set /p "CONFIRM=确认以上配置？[Y/n]: "
if /i "!CONFIRM!"=="n" (
    echo 重新输入...
    goto input_server
)

echo.
echo [1/4] 正在检查 Python 环境...
where python >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 Python！请先安装 Python 3.9+
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo ✅ Python %%v
echo.

echo [2/4] 安装 Python 依赖...
echo     - websocket-client
echo     - Pillow
echo     - pyautogui
echo.
echo ⚠️ 如果安装失败，请手动执行：
echo    pip install websocket-client pillow pyautogui
echo.
pause
pip install websocket-client pillow pyautogui 2>&1 | findstr /i "error warning successfully"
if errorlevel 1 (
    echo.
    echo ⚠️ pip 安装可能失败，请检查错误信息
    echo    常见原因：网络问题、权限不足
    echo    手动安装命令：pip install websocket-client pillow pyautogui
    echo.
    set /p "CONTINUE=是否继续？[y/N]: "
    if /i not "!CONTINUE!"=="y" (
        pause
        exit /b 1
    )
) else (
    echo ✅ 依赖安装完成
)
echo.

echo [3/4] 创建启动脚本...
set "AGENT_DIR=%~dp0"
set "START_SCRIPT=%AGENT_DIR%run_agent.bat"

echo @echo off > "%START_SCRIPT%"
echo chcp 65001 ^>nul >> "%START_SCRIPT%"
echo cd /d "%AGENT_DIR%" >> "%START_SCRIPT%"
echo python winremote_agent.py --server !SERVER_URL! --token !TOKEN! --agent-id !AGENT_ID! >> "%START_SCRIPT%"

echo ✅ 启动脚本已创建: !START_SCRIPT!
echo.
echo     内容预览：
type "%START_SCRIPT%"
echo.

echo [4/4] 关于 NSSM 服务注册...
echo.
echo ⚠️ V0.9.5 不再自动下载 NSSM（安全审查要求）
echo.
echo 如需注册为 Windows 服务（开机自启），请手动操作：
echo   1. 从 https://nssm.cc/download 下载 NSSM
echo   2. 将 nssm.exe 放入 C:\Windows\System32\
echo   3. 管理员运行：nssm install WinRemoteAgent "!START_SCRIPT!"
echo   4. nssm set WinRemoteAgent AppDirectory "!AGENT_DIR!"
echo   5. nssm start WinRemoteAgent
echo.
echo 或者直接使用 agent_admin.bat 菜单管理（选 [5] 安装服务）
echo.

echo ╔══════════════════════════════════════════╗
echo ║             部署完成！                     ║
echo ╠══════════════════════════════════════════╣
echo ║  Agent ID  : !AGENT_ID!                    ║
echo ║  Server    : !SERVER_URL!      ║
echo ║  Agent 目录: !AGENT_DIR!                     ║
echo ╚══════════════════════════════════════════╝
echo.
echo 下一步：
echo   1. 确保服务器端的 AStrBot + WinRemote 插件已运行
echo   2. 直接运行 run_agent.bat 测试连接
echo   3. 或用 agent_admin.bat 安装为系统服务
echo.
echo ⚠️ 安全提醒：
echo   - 确认 Token 已配置为 ≥16 位随机字符
echo   - 正式使用请配合 SSH 隧道，不要裸奔公网！
echo     ssh -N -R 6190:localhost:6190 root@你的服务器IP
echo.
pause
endlocal
