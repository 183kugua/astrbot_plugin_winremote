# WinRemote V0.9.9 用户使用指南

> 适用于 AStrBot 插件 **WinRemote V0.9.9**——通过 QQ 远程控制 Windows 电脑。

---

## 一、快速开始

### 1. 安装插件
1. 在 AStrBot WebUI → 插件市场搜索 **WinRemote** 或直接上传 zip 包
2. 安装后点击「重载插件」
3. 确认插件状态为「已启用」

### 2. 安装 Windows Agent
1. 下载 `winremote_agent.py` 和 `install_agent.bat` 到你的 Windows 电脑
2. 双击 `install_agent.bat`，按提示输入：
   - **Server URL**：`ws://你的服务器IP:6190/winremote`
   - **Token**：和插件配置里的 `secret_token` 一致
   - **Agent ID**：给你的电脑起个名字（如 `home-pc`）
3. 安装完成后 Agent 会作为系统服务自动运行

### 3. 配置插件
在 AStrBot WebUI → 插件 → WinRemote → 设置：

| 配置项 | 建议值 | 说明 |
|---|---|---|
| `secret_token` | `openssl rand -hex 32` 生成 | 和 Agent 端必须一致 |
| `admin_qq` | 你的 QQ 号 | 只有这个 QQ 能控制 |
| `admin_password_hash` | SHA-256 哈希 | 在 Settings 页面生成 |
| `auth_ttl_seconds` | `300` | 授权 5 分钟后自动过期 |
| `enable_llm_mode` | `true` | 开启自然语言控制 |

---

## 二、两种使用方式

### 方式 A：自然语言（推荐，LLM 模式）

开启 `enable_llm_mode` 后，直接对机器人说人话：

| 你说的话 | 机器人做的事 |
|---|---|
| "帮我看下电脑 IP" | 自动执行 `ipconfig /all` |
| "电脑现在卡不卡" | 自动执行 `tasklist` 分析进程 |
| "截个图给我看看" | 自动调用截图工具 |
| "C 盘剩余空间多少" | 自动执行 `dir C:\` |
| "帮我打开记事本" | 自动执行 `notepad.exe` |

> 💡 **原理**：LLM 收到你的话 → 自动选择合适的 Tool → 执行后回复结果

### 方式 B：传统指令（降级通道）

LLM 模式关闭或不可用时的备用方式：

```
/win shell ipconfig /all --pwd 你的密码
/win powershell Get-Process --pwd 你的密码
/win screenshot
/win keypress ctrl+alt+del
/win mouse move 500 300
/win open notepad.exe
/win readfile C:\Temp\test.txt
/win 状态
```

| 指令 | 说明 |
|---|---|
| `/win shell <命令>` | 执行 CMD 命令 |
| `/win powershell <命令>` | 执行 PowerShell 命令 |
| `/win screenshot` | 截取当前桌面 |
| `/win keypress <按键>` | 模拟键盘输入 |
| `/win mouse move <x> <y>` | 移动鼠标 |
| `/win mouse click <按钮>` | 点击鼠标 |
| `/win open <程序>` | 打开程序/文件 |
| `/win readfile <路径>` | 读取文件内容 |
| `/win 状态` | 查看当前授权和连接状态 |

---

## 三、授权机制说明

### TTL 三模式

| `auth_ttl_seconds` 值 | 行为 |
|---|---|
| `1 ~ 1800`（如 300） | 授权后有效期 N 秒，到期自动失效 |
| `0` | **永久授权**，但必须管理员私聊回复"同意"才生效 |
| `> 1800`（如 3600） | 超长授权，同样需要管理员私聊确认 |

### 私聊确认流程

当触发需要确认的操作时：
1. 机器人**私聊你**（不是群里）发送确认消息
2. 你在私聊中回复 **"同意"** → 授权通过
3. 回复 **"拒绝"** 或 **5 分钟不回复** → 自动取消

### 安全命令免确认

以下命令在 `llm_auto_confirm_safe=true` 时**不需要二次确认**：
- `ipconfig` / `tasklist` / `dir` / `whoami` / `systeminfo`
- `Get-Process` / `Get-Service` / `Get-NetIPAddress`

---

## 四、WebUI 面板使用

### Dashboard（仪表盘）
- 实时显示 Agent 在线状态
- 当前授权列表（操作类型 / 剩余时间 / 永久标记）
- 一键吊销单个或全部授权
- 审计完整性检测（HMAC 校验）

### Settings（设置）
- 所有配置项的可视化表单
- SHA-256 密码哈希生成器（输入明文 → 一键复制哈希）
- LLM 模式开关 + 最大调用次数
- 测试连接按钮（显示延迟）

### Logs（日志）
- 所有操作记录（谁、什么时间、执行了什么）
- 按类型筛选（授权事件 / 密码事件）
- 搜索框实时过滤
- HMAC 完整性校验按钮

---

## 五、常见问题

### Q：Agent 连不上服务器？
- 检查防火墙是否放行端口（默认 6190）
- 检查 `secret_token` 两端是否一致
- 用 `telnet 服务器IP 6190` 测试连通性
- 推荐用 SSH 隧道：`ssh -N -R 6190:localhost:6190 root@服务器IP`

### Q：LLM 模式没反应？
- 确认 `enable_llm_mode=true`
- 确认 AStrBot 已配置好 LLM 提供商
- 查看 WebUI → Logs 页面是否有错误
- 临时用 `/win shell xxx` 验证基础功能是否正常

### Q：授权一直过期很烦？
- 把 `auth_ttl_seconds` 调大（最大 3600 秒 = 1 小时）
- 或设为 `0`（永久），但需要每次私聊确认一次

### Q：如何让 Agent 开机自启？
- 用 NSSM 将 `install_agent.bat` 包装为 Windows 服务
- 详见 `WinRemote_NSSM_Service_Guide.md`

---

## 六、安全建议

1. **Token 强度**：用 `openssl rand -hex 32` 生成 64 字符随机串
2. **SSH 隧道**：不要直接把 6190 端口暴露公网
3. **二次密码**：务必设置，即使 QQ 号泄露也有第二道防线
4. **定期轮换**：每隔一段时间换一次 Token 和二次密码
5. **查看审计**：定期在 WebUI Logs 页面检查操作记录

---

## 七、版本更新

| 版本 | 日期 | 核心变化 |
|---|---|---|
| **V0.9.9** | 2026-08-01 | LLM 智能模式 + Skill 注册 + 降级通道 |
| V0.9.6 | 2026-08-01 | 私聊确认 + WebUI 全面升级 |
| V0.9.5 | 2026-07-31 | 会话级授权 + HMAC 审计 |
| V0.9.4 | 2026-07-30 | 首次通过官方审核 |
