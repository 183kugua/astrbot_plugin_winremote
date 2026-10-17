# Changelog

本项目更新日志遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.5.0] - 2026-10-17

### Changed
- 项目更名：Cherry Remote → WinRemote
- 插件标识更名：`astrbot_plugin_cherry_remote` → `astrbot_plugin_winremote`
- 数据目录迁移：`plugin_data/cherry_remote` → `plugin_data/winremote`，首次启动自动迁移旧数据
- 状态查询指令更名：`/cherry` → `/winremote`
- 仓库地址更新为维护者仓库：`github.com/183kugua/astrbot_plugin_winremote`

### Added
- 兼容旧指令：`/cherry` 保留为 `/winremote` 的别名
- README 增加来源声明与原作者署名

## [1.4.0] - 2026-09-24

### Added
- WebSocket 服务端：多设备同时在线，按 device_id 精确路由
- AI 工具集：执行命令、文件读写/拉取、截屏识别、键鼠输入、应用启动、剪贴板、系统信息
- 安全机制：Token 认证、指令权限白名单、急停开关
- 心跳保活与断线重连（指数退避）
- 截屏识别降级：无多模态模型时自动切换视觉转述模型，输出 UI 元素坐标

---
