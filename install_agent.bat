@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

REM ============================================================
REM WinRemote Agent V1.0.0 - Windows 交互式部署脚本
REM 用法：右键「以管理员身份运行」
REM ============================================================

title WinRemote Agent V1.0.0——安装向导

echo.
echo ╔══════════════════════════════════════════╗
echo ║   WinRemote Agent V1.0.0 交互式安装向导   ║
echo ╚══════════════════════════════════════════╝
echo.

REM ============================================================
REM Step 1：收集连接配置
REM ============================================================
echo ┌──────────────────────────────────────────┐
echo │  [1/4] 连接配置                          │
echo └──────────────────────────────────────────┘
echo.

:input_server
set "SERVER_URL="
set /p "SERVER_URL=请输入服务器 WebSocket 地址 [默认: ws://127.0.0.1:1024/w]: "
if "!SERVER_URL!"=="" set SERVER_URL=ws://127.0.0.1:1024/w
echo   ✅ Server URL : !SERVER_URL!
echo.

:input_token
set "TOKEN="
echo ╔══════════════════════════════════════════╗
echo ║        Token 设置                        ║
echo ╚══════════════════════════════════════════╝
echo.
echo   [1] 手动输入 Token
echo   [2] 一键生成随机 Token ^(推荐^)
echo.
set "tok_choice="
set /p "tok_choice=请选择 [1-2，默认 2]: "
if "!tok_choice!"=="" set tok_choice=2

if "!tok_choice!"=="2" (
    echo.
    echo   🔐 正在生成 32 位随机 Token...
    python -c "import secrets;print(secrets.token_hex(32))" > "%TEMP%\wr_token.txt" 2>nul
    if errorlevel 1 (
        echo   ⚠️ Python 未安装或不可用，切换为手动输入
        goto manual_token
    )
    set /p TOKEN=<"%TEMP%\wr_token.txt"
    del "%TEMP%\wr_token.txt" 2>nul
    echo.
    echo   ✅ 随机 Token 已生成！
    echo.
    echo   ┌────────────────────────────────────────────┐
    echo   │ !TOKEN! │
    echo   └────────────────────────────────────────────┘
    echo.
    echo   ⚠️ 请立即复制保存此 Token！服务器端需要配置相同的值。
    echo.

    set /p "TOKEN_CONFIRM=如果已保存，输入 Y 继续: "
    if /i not "!TOKEN_CONFIRM!"=="y" (
        echo   请先复制保存 Token 后重新运行脚本喵~
        pause
        exit /b 1
    )
    goto :input_agent_id
) else (
    :manual_token_input
    echo.
    echo   ⚠️ Token 建议 ≥16 位随机字符！
    echo     推荐生成方式^: python -c "import secrets;print(secrets.token_hex(32))"
    echo     或在线生成: https://www.random.org/strings/
    echo.
    set /p "TOKEN=请输入共享 Token: "
    if "!TOKEN!"=="" (
        echo   ❌ Token 不能为空！
        goto manual_token_input
    )
    if "!TOKEN!"=="change-me" (
        echo   ❌ 不能使用默认值，请输入真实 Token！
        goto manual_token_input
    )
    if "!TOKEN!"=="change-me-to-a-long-random-token" (
        echo   ❌ 不能使用默认值，请输入真实 Token！
        goto manual_token_input
    )
    if "!TOKEN!"=="请换成你的长随机Token" (
        echo   ❌ 不能使用占位文本，请输入真实 Token！
        goto manual_token_input
    )
    call :check_len "!TOKEN!" tok_len
    if !tok_len! LSS 16 (
        echo   ⚠️ Token 长度不足 16 位（当前 !tok_len! 位），安全性较低！
        echo   建议使用 ≥16 位随机字符串。
        set /p "SHORT_OK=仍然使用？[y/N]: "
        if /i not "!SHORT_OK!"=="y" goto manual_token_input
    )
    echo   ✅ Token 已确认（长度 !tok_len! 位）
)

:done_token
:input_agent_id
set "AGENT_ID="
echo.
set /p "AGENT_ID=请输入 Agent 名称 [默认: my-pc-001]: "
if "!AGENT_ID!"=="" set AGENT_ID=my-pc-001
echo   ✅ Agent ID : !AGENT_ID!

echo.
echo ┌──────────────────────────────────────────────┐
echo │  配置确认                                      │
echo │  Server   : !SERVER_URL!                      │
echo │  Token    : [已输入]                            │
echo │  Agent ID : !AGENT_ID!                         │
echo └──────────────────────────────────────────────┘
echo.
set /p "CONFIRM=确认以上配置？[Y/n]: "
if /i "!CONFIRM!"=="n" (
    echo 重新输入...
    goto input_server
)

echo.
echo ┌──────────────────────────────────────────┐
echo │  [2/4] 检查 Python 环境                   │
echo └──────────────────────────────────────────┘
echo.
where python >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 Python！请先安装 Python 3.9+
    echo    下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo ✅ 已检测到 Python %%v
echo.

echo ┌──────────────────────────────────────────┐
echo │  [3/4] 安装 Python 依赖                   │
echo └──────────────────────────────────────────┘
echo.
echo   即将安装：
echo     · websocket-client
echo     · Pillow
echo     · pyautogui
echo.
echo ⚠️ 如果安装失败，请手动执行：
echo    pip install websocket-client pillow pyautogui
echo.
choice /c yn /n /m "是否继续安装？[y/n]: "
if errorlevel 2 (
    echo ⚠️ 跳过依赖安装（需要手动安装后再运行 Agent）
    goto skip_deps
)
echo.
pip install websocket-client pillow pyautogui 2>&1 | findstr /i "error warning successfully already"
if errorlevel 1 (
    echo ⚠️ pip 安装可能遇到问题，请检查错误信息
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
:skip_deps
echo.

echo ┌──────────────────────────────────────────┐
echo │  [4/4] 创建启动脚本                       │
echo └──────────────────────────────────────────┘
set "AGENT_DIR=%~dp0"
set "START_SCRIPT=%AGENT_DIR%run_agent.bat"

echo @echo off > "%START_SCRIPT%"
echo chcp 65001 ^>nul >> "%START_SCRIPT%"
echo title WinRemote Agent V1.0.0——%AGENT_ID% >> "%START_SCRIPT%"
echo cd /d "%AGENT_DIR%" >> "%START_SCRIPT%"
echo python winremote_agent.py --server !SERVER_URL! --token !TOKEN! --agent-id !AGENT_ID! >> "%START_SCRIPT%"

echo ✅ 启动脚本已创建: !START_SCRIPT!
echo.
echo ── 内容预览 ──
type "%START_SCRIPT%"
echo ───────────────

echo.
echo ╔══════════════════════════════════════════╗
echo ║            🎉 部署完成！                   ║
echo ╠══════════════════════════════════════════╣
echo ║  Agent ID  : !AGENT_ID!                    ║
echo ║  Server    : !SERVER_URL!                  ║
echo ╚══════════════════════════════════════════╝
echo.
echo 📌 下一步：
echo   1. 确保 AstrBot + WinRemote 插件已在服务器端运行
echo   2. 双击运行 run_agent.bat 测试连接
echo   3. 或用 agent_admin.bat 安装为 Windows 系统服务（开机自启）
echo.
echo ⚠️ 安全提醒：
echo   · 请确认 Agent 端 Token 与服务器端一致
echo   · 公网连接建议开启 WSS 加密模式
echo.
echo   按任意键退出...
pause >nul
endlocal
exit /b 0

REM ============================================================
REM 工具函数：检查字符串长度
REM ============================================================
:check_len
setlocal EnableDelayedExpansion
set "s=!%~1!"
set "len=0"
if "!s!"=="" goto :check_len_end
:len_loop
if "!s!"=="" goto :check_len_end
set "s=!s:~1!"
set /a len+=1
goto len_loop
:check_len_end
endlocal & set "%~2=%len%"
exit /b 0