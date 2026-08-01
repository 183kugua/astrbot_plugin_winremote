# WinRemote Agent 注册为 Windows 服务 — 极简版

> 5 分钟搞定，让 Agent 开机自启、后台运行、崩溃自恢复。

---

## 步骤 1：准备

```cmd
:: 确认依赖
pip install websocket-client Pillow pyautogui

:: 确认 Agent 能跑通（先手动测一次）
cd C:\WinRemote
python winremote_agent.py
:: 看到 Connected 就 Ctrl+C
```

## 步骤 2：下载 NSSM

1. 打开 https://nssm.cc/download → 下载 nssm 2.24
2. 解压，把 `win64\nssm.exe` 复制到 `C:\WinRemote\nssm.exe`

## 步骤 3：一行命令注册服务

**以管理员身份**打开 CMD：

```cmd
cd C:\WinRemote

nssm install WinRemoteAgent python -u winremote_agent.py
nssm set WinRemoteAgent AppDirectory "C:\WinRemote"
nssm set WinRemoteAgent Start SERVICE_DELAYED_START
nssm set WinRemoteAgent AppRestartDelay 5000
nssm set WinRemoteAgent AppStdout "C:\WinRemote\logs\agent_stdout.log"
nssm set WinRemoteAgent AppStderr "C:\WinRemote\logs\agent_stderr.log"

mkdir C:\WinRemote\logs 2>nul
nssm start WinRemoteAgent
```

## 步骤 4：验证

```cmd
nssm status WinRemoteAgent
:: 应显示 STATE : 4 RUNNING
```

去 QQ 发 `/win status`，看到 Agent 在线 = 成功 ✅

---

## 常用命令速查

```cmd
nssm start   WinRemoteAgent    :: 启动
nssm stop    WinRemoteAgent    :: 停止
nssm restart WinRemoteAgent    :: 重启
nssm status  WinRemoteAgent    :: 状态
nssm remove  WinRemoteAgent confirm  :: 卸载
```

## 排错三板斧

| 现象 | 检查 |
|---|---|
| 启动就停 | `type C:\WinRemote\logs\agent_stderr.log` |
| Running 但连不上 | 等 1 分钟（延迟启动），查 stdout 日志 |
| 键鼠不灵 | 服务默认以 SYSTEM 运行，设成你的用户：`nssm set WinRemoteAgent ObjectName ".\用户名" "密码"` |

---

📖 **完整版教程**（含一键安装脚本、防火墙配置、交互模式等）：见 `WinRemote_NSSM_Service_Guide.md`
