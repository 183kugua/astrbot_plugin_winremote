# WinRemote - AstrBot Remote Control Windows Plugin

通过 QQ 消息远程控制 Windows 主机：执行命令、截图、键鼠模拟、文件读写。

## 架构

```
手机QQ -> NapCat(本机Win) -> AstrBot(服务器)
                                    |
                                    -> WS server :6190
                                         |
                                         -> Windows agent 反连
                                              |- shell / powershell
                                              |- screenshot (Pillow -> base64)
                                              |- pyautogui key/mouse
                                              |- file read/write (path whitelist)


## 一、它能做什么（与不能做什么）

| 功能 |                                     | 默认状态 |             | 开启条件 |
| 受限指令执行                               | ✅ 开 |                | — |
| PowerShell / 任意命令                      | ❌ 关 |                | 会话级临时授权（5 分钟自动过期）+私聊确认
| 文件读取 |                                 | ✅ 开 |                | — |
| 文件写入 |                                 |❌ 关 |                 |临时授权 + 二次密码 |
| 桌面截图 |                                 |✅ 开 |                 |— |
| 键鼠模拟 |                                 |❌ 关 |                 | 临时授权 + 群确认卡片 |
| 审计日志 |                                 |✅ 开（只读） |         | 不可关闭 |

**设计哲学**：RAT 偷偷干，WinRemote 每次都问。所有高危操作必须：
1. 管理员主动申请 → 二次密码验证
2. 群里弹出确认卡片 → 另一管理员点 ✅
3. 授权只活 5 分钟 → 过期自动收回
4. 全程写入防篡改审计日志

## 二、安装

### 1. 服务端（AStrBot 插件端）
3. 进 WebUI → 插件配置，填好：
   - **共享密钥**：≥16 位随机字符（用 `openssl rand -hex 16` 生成）
   - **二次验证密码**：可选，开了所有高危操作都要它
   - 其他保持默认

### 2. Agent 端（被控 Windows 机器）
**方式 A：手动运行（推荐，最安全）**
```
# 直接跑，关掉窗口即停止
python winremote_agent.py
```

**方式 B：注册为 Windows 服务（按需启动）**
```
# 用系统自带的 sc.exe，无需下载任何东西
sc create WinRemoteAgent binPath= "C:\path\to\winremote_agent.py" start= demand
sc description WinRemoteAgent "WinRemote 远程控制 Agent（按需启动）"
# 需要时手动启动：sc start WinRemoteAgent
```

> ⚠️ **关于 NSSM**：本插件**不自动下载** NSSM。如确需，请自行从 https://nssm.cc/download 下载，校验 SHA256 后再用。

## 三、日常使用

### 基础指令（默认可用）
```
/win 状态          查看 Agent 在线状态
/win shell ipconfig 执行白名单内的指令
/win 截图         获取当前桌面
/win ps            查看进程列表
```

### 高危操作（需授权）
```
# 1. 先申请授权（默认为5 分钟有效，可自行调整）
/win auth powershell --pwd 你的二次密码

# 2. 群里弹出确认卡片，另一管理员点 ✅

# 3. 5 分钟内可执行
/win shell powershell Get-Process

# 4. 用完主动收回（可选）
/win revoke powershell
```

## 四、安全自检清单

安装后跑一遍，全过才算安全：
- [ ] `secret_token` ≥ 16 位随机字符
- [ ] `二次验证密码`已设置
- [ ] WebSocket 绑定 `127.0.0.1`（仅本机）或内网 IP，**未映射公网**
- [ ] `allow_powershell` / `allow_write` 在配置页显示为**关闭**
- [ ] `审计日志`路径可访问，文件权限为**只读**
- [ ] 跑 `python auth.py data/logs/winremote_audit.jsonl <你的token>` 输出 `"integrity": true`

## 五、排错

| 现象 | 排查 |
|---|---|
| Agent 连不上 | 检查防火墙是否放行端口、Token 是否一致 |
| 指令被拒 | 看审计日志，是否未授权或已过期 |
| 群卡片不弹 | 确认 AStrBot 版本 ≥ 4.17，且插件已注册卡片处理器 |
| 日志校验失败 | 说明日志被改过，立即吊销 Token 并排查 |

## 六、合规与责任

- 本插件**无后门、无自动下载、无数据外传**
- 所有操作**先写审计再执行**，日志防篡改
- 仅限**授权内网运维**，公网暴露将触发自动熔断
- 漏洞反馈：请在 GitHub 仓库提交 Issue

> 详细安全机制见仓库根目录 `SECURITY.md`。


## QQ 指令

| 指令 | 说明 | 示例 |
|------|------|------|
| `/win 状态` | 所有 Agent 在线/忙碌/离线 | `/win 状态` |
| `/win agents` | 列出已注册 Agent 名 | `/win agents` |
| `/win shell <cmd>` | 执行 Shell 命令 | `/win shell ipconfig` |
| `/win powershell <cmd>` | 执行 PowerShell | `/win powershell Get-Process` |
| `/win 截图` | 返回桌面截图 | `/win 截图` |
| `/win 按键 <keys>` | 模拟按键 | `/win 按键 ctrl+alt+del` |
| `/win 鼠标 <x> <y> <btn>` | 鼠标操作 | `/win 鼠标 500 300 click` |
| `/win 打开 <target>` | 打开程序/文件 | `/win 打开 calc` |
| `/win 读文件 <path>` | 读取文件 (路径白名单) | `/win 读文件 C:\Temp\test.txt` |
| `/win 审计` | 最近 20 条审计记录 | `/win 审计` |

启用二次密码后，每条指令追加 `--pwd xxx`。

## Pages 页面

| 页面 | 路径 | 功能 |
|------|------|------|
| 远控面板 | `/pages/dashboard/` | SSE 实时推送 Agent 状态 |
| 高级配置 | `/pages/settings/` | 可视化编辑所有配置项 |
| 审计日志 | `/pages/logs/` | 分页查看 + 筛选 + 导出 |


**技术亮点：**
- WebSocket 服务端 + Agent 反连架构
- SSH 隧道加密传输
- NSSM 系统服务管理
- AGPL-3.0 开源协议

## 安全建议

1. **必做 SSH 隧道**: `ssh -N -R 6190:localhost:6190 root@服务器IP`
2. **Token 至少 16 位**: `openssl rand -hex 32`
3. **启用二次密码**: 即使 QQ 号泄露也有第二道防线
4. **路径白名单收紧**: 只允许 Agent 访问必要目录
5. **严格白名单模式**: `strict_whitelist=true`

## 已知限制

- 锁屏时 pyautogui 键鼠模拟失效 (shell/截图不受影响)
- Agent 用 `cmd /c` 启动，无法交互式输入
- install_agent.bat 里的变量要手动编辑
- 二次密码 / 加密校验仅服务端做，Agent 侧不校验


> ⚠️ 【最高安全警示】本插为远程控制工具
> ---
> 🔴 绝对禁止行为：
> 2. 使用弱Token（如`123456`、`admin`等易猜解字符串）
> 3. 在未授权设备上安装Agent
> 违反上述要求将导致设备被非法控制，后果自负！
> ---
> 🟡 高风险操作（默认关闭，启用需二次确认）：
> - PowerShell执行、文件写入、键鼠模拟、任意命令执行
> ---
> 🟢 安全操作指引：
> 1. Token长度≥16位随机字符
> 2. 启用二次密码，定期轮换Token
> 3. 查看`SECURITY.md`了解完整安全措施
> 4.插件作者也是为了解决astrbot部署在别的服务器而无法让它使用本机电脑才写的这个插件...
> 📌 合规承诺：本插件无任何后门，所有功能均有审计日志，滥用导致的法律责任由使用者承担。

## 📜 更新日志 (Changelog)

### v0.9.4 
**修复与改进：**
- ✅ 修复 `ruff` Linter 检测到的所有代码规范问题（0 errors）
- ✅ 修正 `Context` 类型注解导入缺失问题（从 `astrbot.api.star` 导入）
- ✅ 自动格式化导入顺序，符合 PEP 8 标准
- ✅ 清理空白行多余字符
- ✅ Schema JSON 完整性验证通过
- 
### v0.9.3
**重大修复：**
- ✅ 修复 `_conf_schema.json` 中 `type: "integer"` 应改为 `"int"` 的错误
- ✅ 统一所有 38 个配置字段使用 AstrBot 支持的白名单类型
- ⚠️ 此版本解决了 Admin 在 v4.26.8 加载失败的紧急问题
- 
### V0.9.0
- ✨ **根因修复**：`_conf_schema.json` 改为 AstrBot 认的扁平结构（不再用分组嵌套）
- ✅ 修复 `string indices must be integers, not 'str'` 加载错误
- ✅ AstrBot `_parse_schema` 现在能正确解析所有 38 个配置项
- ✅ 加 `from __future__ import annotations` 兼容 Python 3.10
- ✅ 保留薄壳 `__init__.py` 供 tests 用 `from astrbot_plugin_winremote import ...`
- ✅ 版本号全文件统一 V0.9.0（py / toml / VERSION / README / bat）
- ✅ 测试 52 个全部通过（FakeWS 替代 MagicMock 解决 async-for 兼容性问题）
- ✅ 修复 `PasswordGuard` 封禁优先级（banned 状态先于密码校验）
- ✅ 扩大 `INJECTION_CHARS` 覆盖 `| `、`>`、`<`、`>>`、`<<`
- ✅ `websockets` 不可用时优雅降级（try/except import）

### V0.6.2
- ✨ 新增 `.astrbot-plugin/i18n/.gitkeep` 占位文件
- ✅ 修复 GitHub UI 将 `.astrbot-plugin/i18n/` 折叠显示为父目录子项的问题
- ✅ 确保 `.astrbot-plugin/i18n/` 在 GitHub 上始终渲染为独立目录
- ✅ 版本号全文件统一 V0.6.2（metadata.yaml / README）

### V0.6.0
- ✨ 新增 `metadata.yaml`（AstrBot 插件身份证，必须文件）
- ✨ 补全 12 个标准字段（name/display_name/desc/short_desc/version/author/repo/tags/astrbot_version/support_platforms/dependencies/license）
- ✅ 修复「加载失败：未找到 metadata.yaml 或 metadata.yml」问题
- ✅ 版本号全文件统一 V0.6.0（__init__.py / webui_panel.py / winremote_agent.py / README）

### V0.5.1
- ✅ 修复 5 个遗留测试 (Mock 异步迭代器 / base_cfg 共享污染 / send side_effect)
- ✅ 52 个测试全部通过 (pytest)
- ✅ ruff check + ruff format 全绿

### V0.5.0
- ✅ 新增 pyproject.toml (ruff 配置)
- ✅ 新增 tests/ 目录 (52 个测试用例)
- ✅ 全部 Python 源码通过 ruff check + ruff format

### V0.4.2
- ✅ 新增 .gitignore + LICENSE (GNU AGPL-3.0，与 AstrBot 官方一致)
