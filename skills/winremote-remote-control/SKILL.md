---
name: winremote-remote-control
description: WinRemote 远程控制 Windows 电脑的技能包。当用户需要查看远程电脑状态、执行系统命令、截图、操控键鼠、读取文件、打开程序时使用。
version: 2.0.0-refactor
author: mijiang
---

# WinRemote 远程控制技能

## 概述

通过 QQ 机器人远程控制一台 Windows 电脑。支持 `/win` 命令 + LLM Tool 自然语言双模式。所有操作都经过会话级授权 + 审计日志记录，安全可控。

## 可用工具（Tools）

| 工具名 | 功能 | 典型场景 |
|---|---|---|
| `win_shell` | 执行 CMD 命令 | 查看 IP、进程、目录、系统信息 |
| `win_powershell` | 执行 PowerShell 命令 | 高级系统管理、WMI 查询、服务管理 |
| `win_screenshot` | 桌面截图 | 查看屏幕内容、确认程序状态 |
| `win_keypress` | 模拟键盘按键 | Ctrl+C 复制、Alt+Tab 切换、Win+R 运行 |
| `win_mouse` | 模拟鼠标操作 | 点击坐标、右键菜单、双击 |
| `win_open` | 打开程序/文件 | 启动计算器、打开文件管理器 |
| `win_agent_status` | 查看电脑在线状态 | 确认 Agent 是否连接、电脑是否开机 |

## 使用策略

### 1. 先观察，再操作

执行操作前，先了解远程电脑状态：
- 用 `win_agent_status` 确认电脑在线
- 用 `win_screenshot` 看屏幕
- 用 `win_shell` 执行 `tasklist` 看进程
- 用 `win_shell` 执行 `ipconfig /all` 看网络

### 2. 命令选择建议

| 用户意图 | 推荐工具 | 示例命令 |
|---|---|---|
| 看电脑在线吗 | `win_agent_status` | 无需参数 |
| 看 IP/网络 | `win_shell` | `ipconfig /all` |
| 看进程 | `win_shell` | `tasklist` 或 `Get-Process`（PS） |
| 看磁盘 | `win_shell` | `wmic logicaldisk get size,freespace,caption` |
| 看系统信息 | `win_shell` | `systeminfo` |
| 管理服务 | `win_powershell` | `Get-Service | Where Status -eq "Running"` |
| 看内存/CPU | `win_powershell` | `Get-Counter '\Memory\Available Mbytes'` |
| 截图确认 | `win_screenshot` | 默认参数即可 |

### 3. 安全规则

- **绝不执行**包含 `rm`/`del`/`format`/`shutdown`/`reboot` 的命令
- **绝不执行**包含管道注入符 `&&` `||` `;` 的拼接命令
- 写入文件、修改注册表等操作需要额外授权，正常情况下不可用
- 所有操作都会被记录到审计日志

### 4. 交互模式

当用户说"帮我看看电脑"时：
1. 先 `win_agent_status` → 确认在线
2. 再截图 → 让用户看到当前桌面
3. 再执行 1-2 个关键命令 → 获取具体信息
4. 汇总结果，用自然语言回复用户

当用户说"帮我打开 XX"时：
1. 直接用 `win_open` 打开程序
2. 截图确认是否成功打开
3. 回复用户结果

## 回复风格

- 用中文回复
- 命令输出过长时，提炼关键信息，不要原样 dump
- 截图成功后，描述截图内容（如"截图显示桌面上有 3 个窗口..."）
- 失败时，解释原因并建议替代方案

## 注意事项

- 如果 Agent 离线（无可用连接），告知用户"远程电脑未连接"
- 如果操作被拒绝（未授权），告知用户"需要先完成授权确认"
- 键鼠模拟在锁屏状态下会失效，截图和命令不受影响
- 每次操作前想一下：这个操作安全吗？会不会影响用户数据？
