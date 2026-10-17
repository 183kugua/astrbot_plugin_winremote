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

## 插件市场条目字段（对应官方 market JSON 规范）

```json
{
  "author": "183kugua",
  "name": "astrbot_plugin_winremote",
  "version": "v1.5.0",
  "repo": "https://github.com/183kugua/astrbot_plugin_winremote",
  "desc": "远程操控连接器：桥接 AstrBot 与远程电脑 App，通过 AI 工具实现远程执行指令。原作者 silver-wolf-little-wife 的 Cherry Remote 改名延续版",
  "display_name": "WinRemote",
  "short_desc": "让 AstrBot 远程操控你的 Windows 电脑",
  "download_url": "https://github.com/183kugua/astrbot_plugin_winremote/releases/download/v1.5.0/astrbot_plugin_winremote-v1.5.0.zip",
  "tags": ["远程控制", "工具", "Windows"],
  "category": "utility",
  "support_platforms": ["aiocqhttp", "qq_official", "telegram", "discord", "slack", "kook", "lark"],
  "social_link": "https://github.com/183kugua/astrbot_plugin_winremote",
  "updated_at": "2026-10-17T21:05:00+08:00"
}
```

> 说明：
> - `author` 必须与 `metadata.yaml` 的 `author` 完全一致，`name` / `version` 同理。
> - `download_url` 需先在 GitHub 建好 `v1.5.0` Release 并上传 zip 后才有效。
> - `support_platforms` 取值需为 AstrBot `ADAPTER_NAME_2_TYPE` 的 key；本插件走 WS，理论上全平台可用。
> - `updated_at` 为 ISO 8601 时间戳。
