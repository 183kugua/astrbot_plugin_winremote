# Changelog

All notable changes to WinRemote will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

---

## [0.9.6] - 2026-08-01

### Added
- **私聊确认授权**：高危操作改为机器人私聊管理员发送申请，回复「同意」通过 / 「拒绝」或5分钟不回复则取消
- **WebUI Dashboard**：授权状态面板 + 一键吊销 + 审计完整性实时检测
- **WebUI Settings**：授权配置组 + SHA-256 密码哈希生成器 + 授权摘要
- **WebUI Logs**：授权事件筛选 + 搜索 + HMAC 校验按钮 + 授权事件标签
- **Widget**：授权状态指示 + 审计完整性实时显示 + 全部吊销/校验按钮
- **测试**：新增 48 个 v0.9.6 专项测试，总测试数 52 → 100，全部通过

### Changed
- 确认方式：群内确认 → 私聊确认（更安全、不打扰群成员）
- confirm.py 超时：60 秒 → 300 秒（5 分钟）
- WebUI 全部页面重构升级

### Fixed
- **`No module named 'auth'` 加载失败**：改用基于 `__file__` 的绝对路径导入，兼容 AStrBot 的 `importlib` 加载方式
- **测试 test_with_agents 失败**：改为直接设置 `srv._running = True`，不依赖 websockets mock
- **测试 test_missing_token_rejected 失败**：增加 `plugin.websockets is None` 分支判断

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

---

## [0.9.4] - 2026-07-30

### Fixed
- 恢复 `main.py` 薄壳入口（官方强制要求）
- Schema 格式：`fields` → `items` 嵌套（官方规范）
- 类型对齐白名单：`integer`→`int`、`boolean`→`bool`、`array`→`list`
- 新增 `requirements.txt`（websockets>=11.0,<16.0）

---

## [0.8.0 ~ 0.9.3] - 2026-07

### Changed (Failed)
- 入口文件改名、Schema 用非官方 `fields` 键、类型不在白名单
- **教训**：`items` vs `fields` 一字之差卡了 5 个版本

---

## [0.7.0] - 2026-06

### Added
- 首个上架版本
- 受限命令执行、桌面截图、文件读写、键鼠模拟、进程管理
- License: AGPL-3.0
