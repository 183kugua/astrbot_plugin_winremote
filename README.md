# WinRemote V0.9.7 - AstrBot Remote Control Windows Plugin

通过 QQ 消息远程控制 Windows 主机：执行命令、截图、键鼠模拟、文件读写。（可跨网络，无需内网穿透）

##  安全警告

**本插件是Astrbot的远程控制工具。**
- 滥用后果自负，作者不承担任何法律责任
- 部署前务必阅读 SECURITY.md
- 无任何恶意代码（已全面审核通过）

## 架构

```
QQ - NapCat(本机Win) - AStrBot(服务器)
 |
 - WS server :6190
 |
 - Windows agent 反连
 |- shell / powershell
 |- screenshot (Pillow - base64)
 |- pyautogui key/mouse
 |- file read/write (path whitelist)
```

### 三模式 TTL

| 配置值 | 含义 | 申请条件 |
|---|---|---|
| 1~1800 秒 | 自定义时长 | 二次密码验证 |
| 0（永久） | 无过期 | 二次密码 + 管理员私聊确认 |
| >1800 秒 | 超长授权 | 二次密码 + 管理员私聊确认 |


### 私聊确认机制

- 需要确认时，机器人**主动私聊管理员**发送申请
- 管理员在**私聊中回复"同意"** → 授权通过
- 管理员回复"拒绝"或**5分钟不回复** → 自动取消
- 非管理员回复 → 忽略
- 支持中英文关键词：同意/确认/yes/agree/允许、拒绝/取消/no/deny/禁止

## 部署步骤

### 1. 服务器: 安装插件

将整个 `astrbot_plugin_winremote/` 目录放入 AStrBot 的 `data/plugins/` 目录。

### 2. 配置: 编辑插件设置

进入 AStrBot WebUI → 插件 → WinRemote → 配置:

**必改项：**
- `secret_token`: 改为 ≥16 位随机字符串
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"

**建议项：**
- `admin_password`: 设置二次密码（SHA-256 哈希更安全）
  ```bash
  python3 -c "import hashlib; print(hashlib.sha256(b'你的密码').hexdigest())"
  ```
- `auth_ttl_seconds`: 授权有效期（默认 300 秒 = 5 分钟）
- `admin_qq`: 填入你的 QQ 号（管理员白名单）

### 3. SSH 隧道 (强烈推荐)

Windows 本机执行:
```bash
ssh -N -R 6190:localhost:6190 root@你的服务器IP
```
这样 Agent 连 `ws://127.0.0.1:6190`，流量走 SSH 加密隧道。

### 4. Windows: 安装 Agent

- 打开本插件github仓库：https://github.com/183kugua/astrbot_plugin_winremote ,下载install_agent.bat和agent_admin.bat两个文件
- 右键 `install_agent.bat` → 以管理员身份运行（已经插件作者本人核查，无危险）
- 脚本会交互式询问 Server URL / Token / Agent ID
- **不再自动下载 NSSM**（安全审查要求）
- 手动下载 NSSM: https://nssm.cc/download
- nssm可以将bat文件包装为windows系统服务，关掉命令行窗口也可以运行
- 使用方法见本插件github仓库中的文档：
- 1.WinRemote_NSSM_Quick_Start.md （5 分钟上手极简版）
- 2.WinRemote_NSSM_Service_Guide.md  （完整教程）
  
  


### 5. Windows: 管理服务

右键 `agent_admin.bat` → 以管理员身份运行（已经插件作者本人核查，无危险）

| 选项 | 功能 |
|---|---|
| [1] 启动 Agent | nssm start WinRemoteAgent |
| [2] 停止 Agent | nssm stop WinRemoteAgent |
| [3] 重启 Agent | nssm restart WinRemoteAgent |
| [4] 查看状态 | 显示服务状态 + 配置摘要 |
| [5] 安装服务 | 交互式安装向导 |
| [6] 卸载服务 | 停止 + 删除服务 |
| [7] 查看日志 | 显示 stdout/stderr 最近 20 行 |
| [8] 编辑配置 | 用记事本打开 run_agent.bat |
| [9] 查看实时输出 | Get-Content -Wait -Tail 10 |

### 6. 验证

服务器终端:
```bash
tail -f ~/.local/share/astrbot/data/winremote/winremote_audit.jsonl
```

QQ 发 `/win 状态`，应返回 Agent 在线信息。

## QQ 指令

| 指令 | 说明 | 示例 |
|---|---|---|
| `/win 状态` | 所有 Agent 在线/忙碌/离线 | `/win 状态` |
| `/win agents` | 列出已注册 Agent 名 | `/win agents` |
| `/win shell <cmd>` | 执行 Shell 命令 | `/win shell ipconfig` |
| `/win powershell <cmd>` | 执行 PowerShell | `/win powershell Get-Process` |
| `/win 截图` | 返回桌面截图 | `/win 截图` |
| `/win 按键 <keys>` | 模拟按键 | `/win 按键 ctrl+alt+del` |
| `/win 鼠标 <x> <y> [btn]` | 鼠标操作 | `/win 鼠标 500 300 click` |
| `/win 打开 <target>` | 打开程序/文件 | `/win 打开 calc` |
| `/win 读文件 <path>` | 读取文件 (路径白名单) | `/win 读文件 C:\Temp\test.txt` |
| `/win 审计` | 最近 20 条审计记录 | `/win 审计` |

> 启用二次密码后，每条指令追加 `--pwd xxx`。
> V0.9.5 起，高危操作还需会话授权（自动弹出私聊确认）。

## 安全建议

1. **必做 SSH 隧道**: `ssh -N -R 6190:localhost:6190 root@服务器IP`
2. **Token 至少 16 位**: `python3 -c "import secrets; print(secrets.token_hex(32))"`
3. **启用二次密码**: 即使 QQ 号泄露也有第二道防线
4. **路径白名单收紧**: 只允许 Agent 访问必要目录
5. **严格白名单模式**: `strict_whitelist=true`
6. **定期轮换 Token**: 建议每 90 天
7. **校验审计日志**: `python auth.py <log_path> <secret_token>`

## 已知限制

- 锁屏时 pyautogui 键鼠模拟失效 (shell/截图不受影响)
- Agent 用 `cmd /c` 启动，无法交互式输入
- 二次密码 / 加密校验仅服务端做，Agent 侧不校验
- 重启插件后所有授权自动失效（安全特性）


## 更新日志

## [0.9.6] - 2026-08-01

### Added
- **私聊确认授权**：高危操作改为机器人私聊管理员发送申请，回复「同意」通过 / 「拒绝」或5分钟不回复则取消
- **WebUI Dashboard**：授权状态面板 + 一键吊销 + 审计完整性实时检测
- **WebUI Settings**：授权配置组 + SHA-256 密码哈希生成器 + 授权摘要
- **WebUI Logs**：授权事件筛选 + 搜索 + HMAC 校验按钮 + 授权事件标签
- **Widget**：授权状态指示 + 审计完整性实时显示 + 全部吊销/校验按钮
- **后端 API**：`/panel/auth.json`（授权详情）、`/panel/auth/revoke`（吊销）、`/panel/audit/verify`（HMAC 校验）
- **测试**：新增 48 个 v0.9.6 专项测试，总测试数 52 → 100，全部通过

### Changed
- 确认方式：群内确认 → 私聊确认（更安全、不打扰群成员）
- confirm.py 超时：60 秒 → 300 秒（5 分钟）
- WebUI 全部页面重构升级

### Security
- HMAC-SHA256 审计签名：所有日志条目防篡改
- 审计日志文件权限设为只读（0o444）
- 非管理员回复私聊确认一律忽略
- 100% 测试通过 / ruff 零警告 / 安全红线全过

---

## [0.9.5] - 2026-07-31

### Added
- **AuthManager**（`auth.py`）：会话级临时授权，支持可配置 TTL
- **confirm.py**：群确认等待回复机制（60 秒超时）
- **HMAC 审计签名**：日志防篡改 + 独立校验脚本

### Changed
- 「永久开关」→「会话级临时授权 + 群确认」
- TTL 三模式：1~1800s 自定义 / 0 永久（需确认）/ >1800s 超长（需确认）
- 删除所有"永久开启"逻辑

### Security
- 每次高危操作必须实时审批
- 授权自动过期，重启后全部失效
- 二次密码 SHA-256 哈希校验

---

## [0.9.4] - 2026-07-30

### Fixed
- 恢复 `main.py` 薄壳入口（官方强制要求）
- Schema 格式：`fields` → `items` 嵌套（官方规范）
- 类型对齐白名单：`integer`→`int`、`boolean`→`bool`、`array`→`list`
- 新增 `requirements.txt`（websockets>=11.0,<16.0）
- `metadata.yaml` 必填字段齐全
- 版本号全链路统一

### Security
- 通过 AStrBot 插件商店审核

---

## [0.8.0 ~ 0.9.3] - 2026-07

### Changed (Failed)
- 入口文件改名、Schema 用非官方 `fields` 键、类型不在白名单
- 反复提交均被审核驳回

### Lesson Learned
> 一个字母之差（`items` vs `fields`）卡了 5 个版本。读官方文档要先于写代码。

---

## [0.7.0] - 2026-06

### Added
- 首个上架版本
- 受限命令执行（ipconfig/tasklist/dir/ps/ls）
- 桌面截图
- 文件读取（白名单目录）
- 文件写入（需授权）
- 键鼠模拟（需授权）
- 进程管理
- 基础审计日志

### Notes
- Schema 扁平结构，类型用官方白名单
- 通过审核，在 AStrBot 插件商店上架
- License: AGPL-3.0
