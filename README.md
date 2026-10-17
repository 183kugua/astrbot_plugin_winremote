# winremote（B 端 · AstrBot 插件）

> 让 AstrBot 成为你的远程电脑遥控器 —— 通过 WebSocket 连接多台
> Windows 电脑，大模型直接帮你操作桌面。

![platform](https://img.shields.io/badge/platform-AstrBot-blue)
![python](https://img.shields.io/badge/python-3.10+-green)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

## 这是什么

本插件是 Cherry Remote 的 **B 端（服务端）**，作为 AstrBot 插件运行。
它维护一个 WebSocket 服务，与一台或多台 Windows 电脑上的 C 端执行器
配对，把大模型的工具调用安全地路由到指定设备。

```text
┌──────────┐   聊天    ┌───────────────┐    WS     ┌────────────────┐
│   用户    │ ───────> │ AstrBot + 插件 │ ────────> │ Windows C 端 xN │
└──────────┘          │   （本插件）    │           │   （另一仓库）   │
                      └───────────────┘           └────────────────┘
                          Token 认证 · 心跳保活 · 权限白名单
```

## 特性

- 🔌 **内置 WS 服务端**：多设备同时在线，按 `device_id` 精确路由
- 🧠 **面向 LLM 的工具集**：执行命令、读写/拉取文件、截屏看屏、
  键鼠输入、启动/搜索应用、剪贴板、系统信息
- 🖼️ **截屏识别**：多模态模型直读屏幕，无多模态时自动降级为视觉转述（输出 UI 元素坐标）
- 🔒 **安全三件套**：Token 认证 + 指令权限白名单 + 急停开关（一键拒绝所有指令）
- 📡 **心跳保活**：断线自动重连（指数退避），设备在线/离线一目了然
- 💬 **自然语言遥控**：聊天里说「帮我看看家里那台电脑的屏幕」就能用

## 快速开始

1. 商店安装，或放入 AstrBot 的 `plugins/` 目录后重载
2. 在 AstrBot WebUI 中配置：监听端口（默认 `8765`）与认证 Token
3. C 端（Windows 执行器）填入相同地址与 Token，设备上线即可对话使用

## 配套项目

- **C 端执行器（Windows）**：Cherry Remote App —— 单文件 exe、托盘常驻、
  内置深色控制台，见另一仓库。

## 安全提示

- 请仅在可信网络中使用，并修改默认 Token
- 指令权限按需开启，不用的高危权限（如 `exec`）可以关闭
- 出门在外不想被遥控？在 C 端控制台打开「急停开关」即可

## License

##本插件参考https://github.com/silver-wolf-little-wife/cherry-astrbot

MIT
