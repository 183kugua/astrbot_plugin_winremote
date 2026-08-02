# WinRemote V0.9.8 - AstrBot Remote Control Windows Plugin

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

## 🤖 V0.9.8 新增：Skill 与 LLM 支持

### **Skill 自然语言调用**
V0.9.8 起，WinRemote 支持通过 **AstrBot Skill 系统** 用自然语言调用远程控制功能喵～

**使用方式：**
```
# 直接对机器人说自然语言
"帮我看看 Windows 主机上有什么进程在运行"
"截取一张远程桌面的图片给我"
"在远程主机上打开计算器"
```

**Skill 会自动：**
1. ✅ 理解主人的自然语言意图
2. ✅ 调用对应的 WinRemote 工具（shell/截图/按键等）
3. ✅ 返回执行结果给主人

### **LLM 工具集成（Function Calling）**
WinRemote 提供标准工具定义（`tools.json`），支持 LLM 函数调用喵～

**可用工具：**
| 工具名 | 功能 | LLM 调用示例 |
|--------|------|-------------|
| `execute_shell` | 执行 Shell 命令 | `execute_shell({"cmd": "ipconfig"})` |
| `execute_powershell` | 执行 PowerShell | `execute_powershell({"cmd": "Get-Process"})` |
| `take_screenshot` | 截取桌面 | `take_screenshot({})` |
| `simulate_keys` | 模拟按键 | `simulate_keys({"keys": "ctrl+alt+del"})` |
| `simulate_mouse` | 模拟鼠标 | `simulate_mouse({"x": 500, "y": 300, "action": "click"})` |
| `open_target` | 打开程序/文件 | `open_target({"target": "calc"})` |
| `read_file` | 读取文件 | `read_file({"path": "C:\\Temp\	est.txt"})` |

**配置方式：**
在 AstrBot 配置中启用 WinRemote Skill：
```yaml
skills:
  - winremote-remote-control  # 启用远程控制 Skill
```

### **优势**
- ✅ **无需记指令**：直接用自然语言描述需求
- ✅ **智能理解**：LLM 自动解析意图并调用正确工具
- ✅ **安全审计**：所有 Skill 调用同样经过授权和审计机制
- ✅ **跨平台兼容**：Skill 定义符合 AstrBot 官方规范

---

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

<<<<<<< HEAD
## [0.9.7] - 2026-08-01

### Fixed
- **`No module named 'auth'` 加载失败**：改用基于 `__file__` 的绝对路径导入，兼容 AStrBot 的 `importlib` 加载方式
- **测试 test_with_agents 失败**：改为直接设置 `srv._running = True`，不依赖 websockets mock
- **测试 test_missing_token_rejected 失败**：增加 `plugin.websockets is None` 分支判断

### Security
- 100% 测试通过 / ruff 零警告 / 安全红线全过
- ✅ 通过 AStrBot 官方审核（VirusTotal 0/65; Claude Code Agent 通过）
=======
## [0.9.8] - 2026-08-02

### Added
- **配置 Schema 全面升级**：对齐 AstrBot 官方最新规范，提升配置可读性与安全性
- **详细配置说明**：每个配置项均附带详细说明，降低新手配置门槛
- **合规性增强**：通过最新安全审计标准，确保插件持续上架

### Changed
- **Schema 格式优化**：进一步完善 `items` 嵌套结构，确保 100% 符合官方校验
- **配置项分类**：将配置按功能模块分组（基础配置、安全配置、授权配置、高级配置）
- **默认值优化**：根据实际使用场景调整默认值，开箱即用更友好

### Fixed
- 修复部分配置项说明不够详细的问题
- 修复版本号全链路对齐问题
- 修复文档与代码版本不一致问题

### Security
- 保持 HMAC-SHA256 审计签名机制
- 保持私聊确认授权机制
- 保持路径白名单严格模式
- 通过 AstrBot 插件商店安全审核

---

## [0.9.7] - 2026-08-01

### Added
- **WebUI 全面重构**：全新 Dashboard/Settings/Logs 三大核心页面
- **授权状态面板**：实时显示当前授权状态、剩余时间、HMAC 校验结果
- **一键吊销功能**：支持单个/全部吊销授权，即时生效
- **审计完整性检测**：实时检测日志是否被篡改，异常立即告警
- **授权事件筛选**：支持按 Agent ID、事件类型、时间范围筛选日志
- **搜索功能**：支持关键词搜索审计日志
- **Widget 组件**：快速查看授权状态、审计完整性、一键操作按钮
- **后端 API**：`/panel/auth.json`、`/panel/auth/revoke`、`/panel/audit/verify`

### Changed
- WebUI 全部页面重构升级，UI/UX 全面优化
- 确认方式：群内确认 → 私聊确认（更安全、不打扰群成员）
- confirm.py 超时：60 秒 → 300 秒（5 分钟）

### Security
- HMAC-SHA256 审计签名：所有日志条目防篡改
- 审计日志文件权限设为只读（0o444）
- 非管理员回复私聊确认一律忽略
- 100% 测试通过 / ruff 零警告 / 安全红线全过
>>>>>>> 2cfd086 (📝 更新 v0.9.8 更新日志 + 补充 v0.9.7 记录)

---

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
