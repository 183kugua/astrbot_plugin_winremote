# WinRemote V0.9.5 - AstrBot Remote Control Windows Plugin

通过 QQ 消息远程控制 Windows 主机：执行命令、截图、键鼠模拟、文件读写。（可跨网络，无需内网穿透）

## ⚠️ 安全警告

**本插件是Astrbot的远程控制工具。**
- 仅限授权内网运维场景使用
- 滥用后果自负，作者不承担任何法律责任
- 部署前务必阅读 SECURITY.md

## 许可证

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)**，与 AstrBot 主项目保持一致。
详见 `LICENSE` 文件。redistributing 时请保留版权声明。

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
```

### 审计日志 HMAC 签名

每条审计记录都附带 HMAC-SHA256 签名，防止篡改：

```bash
# 校验审计日志完整性
python auth.py data/winremote_audit.jsonl your-secret-token
# 输出: {"ok_count": 152, "tampered_lines": [], "integrity": true}
```


## 部署步骤

### 1. 服务器: 安装插件

将整个 `astrbot_plugin_winremote/` 目录放入 AStrBot 的 `data/plugins/` 目录。

### 2. 配置: 编辑插件设置

进入 AStrBot WebUI → 插件 → WinRemote → 配置:

**必改项：**
- `secret_token`: 改为 ≥16 位随机字符串
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```

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

右键 `install_agent.bat` → 以管理员身份运行（在本插件的github仓库里，已经插件作者本人核查）
- 脚本会交互式询问 Server URL / Token / Agent ID
- **不再自动下载 NSSM**（安全审查要求）
- 手动下载 NSSM: https://nssm.cc/download
-nssm可以将bat文件包装为windows系统服务，关掉命令行窗口也可以运行

### 5. Windows: 管理服务

右键 `agent_admin.bat` → 以管理员身份运行（在本插件的github仓库里，已经插件作者本人核查）

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

## 升级历史

### V0.9.5 (当前)
- ✨ **新增** `auth.py`：会话级临时授权 + HMAC-SHA256 审计签名
- ✨ **新增** `confirm.py`：私聊确认等待回复机制
- ✨ **新增** `auth_ttl_seconds` 配置项（可配置授权有效期）
- 🔒 删除所有"永久开关"逻辑，改为"默认关闭 + 临时授权 + 自动过期"
- 🔒 高危操作（PowerShell/写入/键鼠）需私聊确认才授予永久权限
- 🔒 重启插件后所有授权自动失效
- 🔒 `install_agent.bat` 改为交互式，删除自动下载逻辑
- 📝 审计日志增加 HMAC 签名，可用 `verify_audit()` 校验完整性

### V0.9.4
- ✅ 修复 ruff Linter 检测到的所有代码规范问题（0 errors）
- ✅ 修正 Context 类型注解导入缺失问题
- ✅ 自动格式化导入顺序，符合 PEP 8 标准
- ✅ 清理空白行多余字符
- ✅ Schema JSON 完整性验证通过

### V0.9.3
- ✅ 修复 `_conf_schema.json` 中 type: "integer" 应改为 "int"
- ✅ 统一所有配置字段使用 AStrBot 支持的白名单类型

### V0.9.0
- ✨ 根因修复：`_conf_schema.json` 改为 AStrBot 认的扁平结构
- ✅ 修复 `string indices must be integers` 加载错误
- ✅ 加 `from __future__ import annotations` 兼容 Python 3.10
- ✅ 测试 52 个全部通过
- ✅ 修复 `PasswordGuard` 封禁优先级
- ✅ 扩大 `INJECTION_CHARS` 覆盖
