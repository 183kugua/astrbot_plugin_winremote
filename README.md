# WinRemote Plugin for AstrBot

远程控制 Windows 电脑的 AstrBot 插件。

## 架构

```
astrbot_plugin_winremote/
├── plugin.py           # 主入口（瘦客户端）
├── config.py           # 类型化配置
├── models.py           # 数据模型
├── security.py         # 安全校验
├── auth.py             # 认证管理
├── server.py           # HTTP 服务器
├── tool_handlers.py    # 工具处理器
├── tools.py            # 工具定义
├── _conf_schema.json   # 配置 Schema
├── metadata.yaml       # 插件元数据
├── pyproject.toml      # Python 项目配置
├── pages/              # 前端页面
│   └── index.html
├── agent/              # Agent 端（运行在 Windows）
│   ├── winremote_agent.py
│   ├── start_agent.bat
│   ├── agent_config.example.json
│   └── tests/
├── skills/             # AstrBot Skills
│   └── winremote-remote-control/
└── tests/              # 单元测试
```

## 安装

### 服务端（AstrBot）

```bash
# 进入插件目录
cd astrbot_plugin_winremote

# 安装依赖
pip install -e .
```

### 客户端（Windows 远程电脑）

1. 复制 `agent/` 目录到 Windows 电脑
2. 编辑 `agent_config.example.json` 为 `agent_config.json`
3. 配置服务器地址和 Token
4. 运行 `start_agent.bat`

## 配置

编辑 `data/plugins/astrbot_plugin_winremote/config.json`:

```json
{
  "server_port": 8765,
  "auth_token": "your_secure_token_here",
  "allowed_commands": ["ipconfig", "tasklist", "dir", "systeminfo"],
  "allowed_paths": ["C:/Users", "D:/", "E:/"],
  "block_sensitive": true,
  "max_output_length": 5000,
  "screenshot_quality": 75,
  "session_timeout_minutes": 30
}
```

## 工具列表

| 工具名 | 描述 |
|--------|------|
| win_shell | 执行 CMD 命令 |
| win_powershell | 执行 PowerShell 命令 |
| win_screenshot | 截取屏幕（返回图片） |
| win_keypress | 模拟键盘按键 |
| win_mouse | 模拟鼠标操作 |
| win_open | 打开程序/文件/URL |
| win_type | 模拟键盘输入文本 |
| win_agent_status | 查看 Agent 状态 |

## 安全特性

- ✅ Token 认证
- ✅ 命令白名单
- ✅ 路径白名单
- ✅ 敏感操作拦截
- ✅ 命令长度限制
- ✅ 危险字符过滤

## 开发

```bash
# 运行测试
pytest tests/ -v

# 代码格式化
black astrbot_plugin_winremote/

# 代码检查
ruff check astrbot_plugin_winremote/
```

## 版本

2.0.0-refactor - 完全重构版本

## 许可证

MIT
