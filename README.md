# WinRemote V0.6.0 - AstrBot Remote Control Windows Plugin

通过 QQ 消息远程控制 Windows 主机：执行命令、截图、键鼠模拟、文件读写。
“本插件几乎全为AI编写（这条内容除外~）”
允许任何人基于本继续改进

## 许可证

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)**，与 AstrBot 主项目保持一致。
详见 `LICENSE` 文件。redistributing 时请保留版权声明。

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
```

## 文件结构 (V0.6.0)

```
astrbot_plugin_winremote/
├── metadata.yaml            ✨ V0.6.0 新增：AstrBot 插件身份证（必须）
├── .gitignore               # Git 忽略规则
├── LICENSE                  # GNU AGPL-3.0
├── __init__.py              # 插件主体 (WS 服务端 + 指令 + Web API)
├── _conf_schema.json        # 配置 Schema (8 大分组, 38 字段)
├── winremote_agent.py       # Windows Agent (反连 WS + 动作分发)
├── webui_panel.py          # 主面板小组件 (后端 + 前端)
├── install_agent.bat        # Windows 一键部署
├── agent_admin.bat         # Windows 服务管理菜单
├── README.md                # 本文件
├── pyproject.toml          # ruff + pytest 配置
├── tests/                   # 测试代码 (52 个用例)
│   ├── __init__.py
│   ├── test_config.py       # 配置 / 校验 / 审计
│   ├── test_security.py     # Token / 密码 / 注入拦截
│   └── test_agent_protocol.py  # Agent 生命周期 / SSE
├── pages/
│   ├── dashboard/          # 实时状态面板 (SSE)
│   ├── settings/           # 可视化配置页
│   └── logs/              # 审计日志查看器
└── .astrbot-plugin/i18n/
    ├── zh-CN.json
    └── en-US.json
```

## metadata.yaml 字段说明

| 字段 | 是否必须 | 说明 |
|---|---|---|
| `name` | ✅ 必须 | 插件唯一标识，**必须与目录名完全一致**（AstrBot 靠它识别插件） |
| `display_name` | 可选 | WebUI / 插件市场展示名（v4.5.0+） |
| `desc` | ✅ 必须 | 插件完整描述 |
| `short_desc` | 可选 | 插件卡片一句话摘要 |
| `version` | ✅ 必须 | 版本号，必须带 `v` 前缀，如 `v0.6.0` |
| `author` | ✅ 必须 | 作者名 |
| `repo` | ✅ 必须 | 源代码仓库地址 |
| `tags` | 可选 | 插件市场标签数组 |
| `astrbot_version` | 可选 | 依赖的 AstrBot 版本范围（PEP 440，不带 v 前缀） |
| `support_platforms` | 可选 | 支持的适配器平台列表（不填则支持所有） |
| `dependencies` | 可选 | 依赖的其他插件名称数组 |
| `license` | 可选 | 许可证标识 |

> ⚠️ **重要**：`name` 字段必须与插件目录名一致，否则 AstrBot 会报
> `压缩包不是合法的 AstrBot 插件: 未找到 metadata.yaml 或 metadata.yml`

## 部署步骤



### 1. 服务器: 安装插件

```bash
cp -r astrbot_plugin_winremote/ ~/.local/share/astrbot/data/plugins/
sudo systemctl restart astrbot
```

### 2. WebUI 配置

进入 AstrBot WebUI -> 插件 -> WinRemote -> 配置:
- `secret_token`: 填一个长随机字符串 (建议 `openssl rand -hex 32`)
- `admin_qq`: 填你的 QQ 号 (数组格式)
- `ws_host`: 强烈建议 `127.0.0.1`
- 其他按需调整

### 3. SSH 隧道 (强烈推荐)

Windows 本机执行:
```bash
ssh -N -R 6190:localhost:6190 root@你的服务器IP
```
这样 Agent 连 `ws://127.0.0.1:6190`，流量走 SSH 加密隧道。

### 4. Windows: 安装 Agent

右键 `install_agent.bat` -> 以管理员身份运行
- 编辑 bat 顶部 3 个变量: `SERVER_URL` / `TOKEN` / `AGENT_ID`
- 脚本自动装依赖 -> 下 NSSM -> 注册服务 -> 开机自启

### 5. Windows: 管理服务

右键 `agent_admin.bat` -> 以管理员身份运行

| 选项 | 功能 |
|------|------|
| [1] 启动 Agent | `nssm start WinRemoteAgent` |
| [2] 停止 Agent | `nssm stop WinRemoteAgent` |
| [3] 重启 Agent | `nssm restart WinRemoteAgent` |
| [4] 查看状态 | 显示服务状态 + 配置摘要 |
| [5] 安装服务 | 交互式安装向导 |
| [6] 卸载服务 | 停止 + 删除服务 |
| [7] 查看日志 | 显示 stdout/stderr 最近 20 行 |
| [8] 编辑配置 | 用记事本打开 run_agent.bat |
| [9] 查看实时输出 | `Get-Content -Wait -Tail 10` |

### 6. 验证

服务器终端:
```bash
tail -f ~/.local/share/astrbot/data/winremote/audit.jsonl
```
QQ 发 `/win 状态`，应返回 Agent 在线信息。

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

## V0.5 新增: 测试

V0.5 开始附带完整测试套件，覆盖:
- 配置加载与缺省兜底
- 四重命令校验 (黑名单 / 注入 / 正则 / 白名单)
- Token 认证与二次密码
- Agent 注册 / 心跳 / 离线判定 / 任务分发
- 审计日志读写与轮转
- Web API (SSE / 审计 / 设置 / Ping)

运行测试:
```bash
pip install pytest pytest-asyncio ruff
pytest tests/ -v
```

代码质量:
```bash
ruff check .          # lint
ruff format --check .  # format check
ruff format .          # auto-format
```

## V0.5.1 修复

| 问题 | 根因 | 修复 |
|------|------|------|
| test_handshake_success 失败 | agent 在 finally 中被移除后断言 | 改为检查 ws.send 调用 |
| test_heartbeat_keeps_alive 失败 | 同上 | 改为检查 heartbeat_ack 发送 |
| test_invalid_json_ignored 失败 | 迭代器耗尽后 agent 被移除 | 改为检查 send 日志 |
| test_sends_and_waits 失败 | agent.authenticated 未设置 | 测试中显式设置 |
| test_missing_token_rejected 失败 | recv 立即抛异常跳过校验 | recv 先返回消息再关闭 |

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

## 开发原则合规

- [x] 功能经过测试 (52 个用例全部通过)
- [x] 包含良好注释和类型注解
- [x] 持久化数据存 data/ 目录
- [x] 良好错误处理，单点失败不崩溃插件
- [x] 使用 ruff 格式化 (ruff check + ruff format)
- [x] 未使用 requests 库 (纯 WebSocket 异步)
- [x] 功能为新插件 (非扩增现有插件)

## 升级历史

### V0.6.0 (当前)
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
