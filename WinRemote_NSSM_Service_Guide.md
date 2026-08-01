# WinRemote Agent 注册为 Windows 系统服务教程

> 用 NSSM (Non-Sucking Service Manager) 把 `winremote_agent.py` 包装成 Windows 服务，实现 **开机自启、崩溃自动重启、无窗口后台运行**。

---

## 一、为什么要用 NSSM

直接双击 `install_agent.bat` 启动 Agent 有几个痛点：

| 问题 | NSSM 解决方案 |
|---|---|
| 关机/重启后不会自动运行 | ✅ 注册为服务，开机自启 |
| 运行在 CMD 窗口里，容易被误关 | ✅ 完全后台，无窗口 |
| 程序崩溃后需要手动重启 | ✅ 可配置崩溃自动重启 |
| 多用户登录时归属混乱 | ✅ 以 SYSTEM 或指定账户运行 |

---

## 二、准备工作

### 1. 确认 Python 环境

```cmd
python --version
pip list | findstr -i "websocket pillow pyautogui"
```

确保以下依赖已安装：
```
websocket-client
Pillow
pyautogui
```

> 缺什么装什么：`pip install websocket-client Pillow pyautogui`

### 2. 确认 Agent 能正常启动

先手动跑一次，确保配置正确：

```cmd
cd C:\WinRemote
python winremote_agent.py
```

看到类似 `✅ Connected to server` 的日志就 Ctrl+C 关掉，继续下一步。

### 3. 下载 NSSM

1. 打开官网：https://nssm.cc/download
2. 下载 **nssm 2.24**（或最新稳定版）
3. 解压后，根据你的系统架构选：
   - 64 位系统 → 用 `nssm.exe`（在 `win64` 文件夹里）
   - 32 位系统 → 用 `nssm.exe`（在 `win32` 文件夹里）

> 💡 **建议**：把 `nssm.exe` 复制到 `C:\WinRemote\nssm.exe`，和 Agent 放一起，方便管理。

验证：
```cmd
C:\WinRemote\nssm.exe version
```
看到版本号就 OK。

---

## 三、注册为 Windows 服务（核心步骤）

### 方式 A：命令行一键注册（推荐）

**以管理员身份**打开 CMD，执行：

```cmd
cd C:\WinRemote

nssm install WinRemoteAgent python -u winremote_agent.py
```

参数说明：
| 参数 | 含义 |
|---|---|
| `WinRemoteAgent` | 服务名称（自定义，后面管理用这个名） |
| `python` | 可执行程序 |
| `-u winremote_agent.py` | 参数：`-u` 表示 unbuffered（实时输出日志），后面是脚本路径 |

### 方式 B：图形界面注册

```cmd
nssm install WinRemoteAgent
```

会弹出 GUI 窗口，按以下填写：

**Application 标签页：**

| 字段 | 填写内容 |
|---|---|
| Path | `C:\Python311\python.exe`（你的 Python 路径） |
| Startup directory | `C:\WinRemote` |
| Arguments | `-u winremote_agent.py` |

**Details 标签页：**

| 字段 | 填写内容 |
|---|---|
| Display name | `WinRemote Agent` |
| Description | `WinRemote WebSocket Agent - 远程控制代理` |
| Startup type | `Automatic (Delayed Start)`（推荐延迟启动，等网络就绪） |

**I/O 标签页（日志重定向）：**

| 字段 | 填写内容 |
|---|---|
| Output (stdout) | `C:\WinRemote\logs\agent_stdout.log` |
| Error (stderr) | `C:\WinRemote\logs\agent_stderr.log` |

> 先创建目录：`mkdir C:\WinRemote\logs`

点 **Install service** 完成注册。

---

## 四、配置服务属性

### 1. 设置自动重启（崩溃恢复）

```cmd
nssm set WinRemoteAgent AppRestartDelay 5000
```

含义：程序意外退出后，**5 秒后自动重启**。

### 2. 设置启动类型

```cmd
:: 开机自动启动（默认）
nssm set WinRemoteAgent Start SERVICE_AUTO_START

:: 或者：延迟启动（推荐，等网络就绪后再连）
nssm set WinRemoteAgent Start SERVICE_DELAYED_START
```

### 3. 设置运行账户

默认以 `Local System` 运行（权限最高），但有些场景需要指定用户：

```cmd
:: 以当前用户身份运行（能访问用户桌面，键鼠模拟更可靠）
nssm set WinRemoteAgent ObjectName ".\你的用户名" "你的密码"
```

> ⚠️ **键鼠模拟注意**：`pyautogui` 需要能访问桌面会话。如果以 SYSTEM 运行但桌面锁屏了，键鼠会失效。建议：
> - 要么不锁屏
> - 要么用 `ObjectName` 指定一个已登录的用户

### 4. 环境变量（如果需要）

如果 Python 不在系统 PATH 里，或者需要额外环境变量：

```cmd
nssm set WinRemoteAgent AppEnvironmentExtra "PATH=C:\Python311;C:\Python311\Scripts;%PATH%"
```

---

## 五、启动 / 停止 / 卸载

### 日常操作命令

```cmd
:: 启动服务
nssm start WinRemoteAgent
net start WinRemoteAgent

:: 停止服务
nssm stop WinRemoteAgent
net stop WinRemoteAgent

:: 重启服务
nssm restart WinRemoteAgent

:: 查看服务状态
nssm status WinRemoteAgent
sc query WinRemoteAgent

:: 查看实时日志
type C:\WinRemote\logs\agent_stdout.log
:: 或实时跟踪
powershell "Get-Content C:\WinRemote\logs\agent_stdout.log -Tail 20 -Wait"
```

### 卸载服务

```cmd
:: 先停止
nssm stop WinRemoteAgent

:: 再删除
nssm remove WinRemoteAgent confirm
```

> `confirm` 参数是跳过确认提示，不加的话会弹窗问你一次。

---

## 六、验证服务正常运行

### 1. 检查服务状态

```cmd
sc query WinRemoteAgent
```

关注这几行：
```
STATE              : 4  RUNNING    ← 必须是 RUNNING
WIN32_EXIT_CODE    : 0  (0x0)     ← 无错误
```

### 2. 检查 Agent 连接

```cmd
powershell "Get-Content C:\WinRemote\logs\agent_stdout.log -Tail 30"
```

应该看到：
```
[2026-08-01 14:23:01] ✅ Connected to ws://your-server-ip:6190
[2026-08-01 14:23:01] 🔐 Token verified, authenticated
[2026-08-01 14:23:01] 💓 Heartbeat started
```

### 3. 从 AStrBot 端验证

在 QQ 里发：
```
/win status
```

应该能看到 Agent 在线。

---

## 七、开机自启测试

1. **重启电脑**（不要只是注销）
   ```cmd
   shutdown /r /t 0
   ```
2. 等系统完全启动（约 1-2 分钟，延迟启动要等网络就绪）
3. 不登录任何用户，**直接**用另一台设备从 QQ 发指令测试
4. 如果能正常响应 → ✅ 服务配置成功

---

## 八、常见问题排查

### ❌ 服务启动后立即停止（Exit Code 1）

**原因**：脚本路径错、Python 找不到、依赖缺失。

**排查**：
```cmd
:: 查看错误日志
type C:\WinRemote\logs\agent_stderr.log

:: 手动用同样的命令跑一下，看报什么错
cd C:\WinRemote
python -u winremote_agent.py
```

### ❌ 服务显示 Running 但 Agent 没连上服务器

**原因**：网络未就绪时服务就启动了，连接失败后没重试。

**解决**：改成延迟启动 + 让 Agent 端有重连逻辑（v0.9.6 的 Agent 已有自动重连）。

```cmd
nssm set WinRemoteAgent Start SERVICE_DELAYED_START
nssm set WinRemoteAgent AppRestartDelay 10000
```

### ❌ 键鼠模拟不生效

**原因**：服务以 SYSTEM 运行，无法访问用户桌面会话。

**解决**：
```cmd
:: 改为以当前用户运行
nssm set WinRemoteAgent ObjectName ".\你的用户名" "你的密码"
nssm restart WinRemoteAgent
```

或者设置允许服务与桌面交互（不推荐，安全性差）：
```cmd
nssm set WinRemoteAgent Type SERVICE_INTERACTIVE_PROCESS
```

### ❌ 端口被防火墙拦了

```cmd
:: 放行出站 WebSocket 端口（默认 6190）
netsh advfirewall firewall add rule name="WinRemote Agent" dir=out action=allow protocol=TCP localport=6190

:: 如果是入站（Agent 端做服务端才需要）
netsh advfirewall firewall add rule name="WinRemote Agent" dir=in action=allow protocol=TCP localport=6190
```

> Agent 是**出站连接**（连香港服务器），一般家用防火墙默认放行出站，通常不用配。

---

## 九、完整一键安装脚本

把以下内容保存为 `install_as_service.bat`，**右键 → 以管理员身份运行**：

```batch
@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ╔══════════════════════════════════════╗
echo ║   WinRemote Agent → Windows 服务安装   ║
echo ╚══════════════════════════════════════╝
echo.

:: 1. 确认路径
set "AGENT_DIR=%~dp0"
set "NSSM=%AGENT_DIR%nssm.exe"
set "PYTHON=python.exe"

:: 2. 检查 Python
%PYTHON% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [✗] Python 未安装或未加入 PATH
    echo     请先安装 Python 3.10+ 并勾选 "Add to PATH"
    pause
    exit /b 1
)
echo [✓] Python 已就绪

:: 3. 检查 NSSM
if not exist "%NSSM%" (
    echo [✗] nssm.exe 不在当前目录
    echo     请从 https://nssm.cc/download 下载并放到 %AGENT_DIR%
    pause
    exit /b 1
)
echo [✓] NSSM 已就绪

:: 4. 安装依赖
echo.
echo [..] 安装/更新 Python 依赖...
%PYTHON% -m pip install -q --upgrade websocket-client Pillow pyautogui 2>&1
echo [✓] 依赖安装完成

:: 5. 创建日志目录
if not exist "%AGENT_DIR%logs" mkdir "%AGENT_DIR%logs"
echo [✓] 日志目录就绪

:: 6. 如果已存在旧服务，先卸载
%NSSM% status WinRemoteAgent >nul 2>&1
if %errorlevel% equ 0 (
    echo [..] 检测到旧服务，正在卸载...
    %NSSM% stop WinRemoteAgent >nul 2>&1
    %NSSM% remove WinRemoteAgent confirm >nul 2>&1
    echo [✓] 旧服务已卸载
)

:: 7. 注册新服务
echo.
echo [..] 注册 WinRemoteAgent 服务...
%NSSM% install WinRemoteAgent %PYTHON% -u "%AGENT_DIR%winremote_agent.py" >nul
if %errorlevel% neq 0 (
    echo [✗] 服务注册失败
    pause
    exit /b 1
)
echo [✓] 服务注册成功

:: 8. 配置服务属性
%NSSM% set WinRemoteAgent AppDirectory "%AGENT_DIR%" >nul
%NSSM% set WinRemoteAgent DisplayName "WinRemote Agent" >nul
%NSSM% set WinRemoteAgent Description "WinRemote WebSocket Agent - 远程控制代理服务" >nul
%NSSM% set WinRemoteAgent Start SERVICE_DELAYED_START >nul
%NSSM% set WinRemoteAgent AppRestartDelay 5000 >nul
%NSSM% set WinRemoteAgent AppStdout "%AGENT_DIR%logs\agent_stdout.log" >nul
%NSSM% set WinRemoteAgent AppStderr "%AGENT_DIR%logs\agent_stderr.log" >nul
%NSSM% set WinRemoteAgent AppRotateFiles 1 >nul
%NSSM% set WinRemoteAgent AppRotateBytes 1048576 >nul
echo [✓] 服务属性配置完成

:: 9. 启动服务
echo.
echo [..] 启动服务...
%NSSM% start WinRemoteAgent
timeout /t 3 /nobreak >nul

:: 10. 验证
%NSSM% status WinRemoteAgent | findstr "SERVICE_RUNNING" >nul
if %errorlevel% equ 0 (
    echo.
    echo ╔══════════════════════════════════════╗
    echo ║  ✅ WinRemote Agent 服务安装成功！     ║
    echo ║                                      ║
    echo ║  服务名: WinRemoteAgent               ║
    echo ║  启动类型: 延迟自动启动               ║
    echo ║  崩溃恢复: 5秒后自动重启              ║
    echo ║  日志目录: logs\                      ║
    echo ╚══════════════════════════════════════╝
    echo.
    echo 常用命令：
    echo   启动:  nssm start WinRemoteAgent
    echo   停止:  nssm stop WinRemoteAgent
    echo   日志:  type logs\agent_stdout.log
    echo   卸载:  nssm remove WinRemoteAgent confirm
) else (
    echo.
    echo [✗] 服务启动失败，查看日志：
    type "%AGENT_DIR%logs\agent_stderr.log"
)

echo.
pause
```

---

## 十、服务管理速查表

| 操作 | 命令 |
|---|---|
| 安装服务 | `nssm install WinRemoteAgent python -u winremote_agent.py` |
| 启动 | `nssm start WinRemoteAgent` |
| 停止 | `nssm stop WinRemoteAgent` |
| 重启 | `nssm restart WinRemoteAgent` |
| 状态 | `nssm status WinRemoteAgent` |
| 编辑配置（GUI） | `nssm edit WinRemoteAgent` |
| 查看参数 | `nssm get WinRemoteAgent <参数名>` |
| 设置参数 | `nssm set WinRemoteAgent <参数名> <值>` |
| 删除服务 | `nssm remove WinRemoteAgent confirm` |
| 设为延迟启动 | `nssm set WinRemoteAgent Start SERVICE_DELAYED_START` |
| 崩溃5秒后重启 | `nssm set WinRemoteAgent AppRestartDelay 5000` |
| 日志轮转1MB | `nssm set WinRemoteAgent AppRotateBytes 1048576` |

---

## 十一、安全提醒

| 风险 | 建议 |
|---|---|
| 服务以 SYSTEM 运行权限过高 | 用 `ObjectName` 指定普通用户 |
| 日志可能含敏感信息 | 定期清理 `logs\` 目录，或设日志轮转 |
| Agent 连公网服务器 | 确保 `secret_token` 用 `openssl rand -hex 32` 生成，**别用弱密码** |
| 服务可被管理员停止 | 这是正常行为，不要试图隐藏服务 |

---

**教程结束。** 装好后你的 WinRemote Agent 就会像系统服务一样默默运行，开机自启、崩溃自恢复，完全不需要人工干预。
