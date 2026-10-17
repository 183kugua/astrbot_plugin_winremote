<h3 align="center">⚠️ 双仓库协作项目 / Two-Repo Project</h3>
<p align="center"><b>本项目需要两个仓库共同部署才能完整运作：</b></p>
<p align="center">
<a href="https://github.com/183kugua/astrbot_plugin_winremote"><b>winremote-astrbot</b></a>（B 端 · AstrBot 插件） ↔ <a href="https://github.com/183kugua/winremote-app"><b>winremote-app</b></a>（C 端 · 执行器）
</p>

> [!IMPORTANT]
> 本仓库是 **B 端 AstrBot 插件**，必须与 **C 端执行器 [winremote-app](https://github.com/183kugua/winremote-app)** 配合部署。请同时获取两个仓库。

---

# astrbot_plugin_winremote

> **⚠️ 来源声明**：本仓库是原作者 [@silver-wolf-little-wife](https://github.com/silver-wolf-little-wife) 的 **Cherry Remote**（[cherry-astrbot](https://github.com/silver-wolf-little-wife/cherry-astrbot) / [cherry-remote-app](https://github.com/silver-wolf-little-wife/cherry-remote-app)）的改名延续版（WinRemote），由 [@183kugua](https://github.com/183kugua) 维护。原作者享有原始作品的全功劳，本项目遵循原开源协议（MIT）。


**WinRemote** —— AstrBot 远程操控连接器。当前版本 **v1.5.0**。

桥接 AstrBot（B地·云服务器）与远程电脑上的 winremote-app（C地·家庭局域网 PC），实现「手机发需求 → AstrBot 调 AI 生成指令 → 插件转发 → 远程电脑执行 → 结果回传 B 端研判 → 回复原会话」的完整闭环。

## 定位

本插件是**纯连接器**，不承载 AI 生成逻辑：

- 内嵌 WebSocket 服务端，接受 C 端 App 主动外连（穿透 NAT）。
- 注册 FunctionTool，AstrBot Agent 在普通对话中自主调用。
- 回收执行结果回传 Agent 研判。

## 已注册工具

| 工具 | 能力 |
|---|---|
| `remote_exec` | 远程执行 shell 命令 |
| `remote_sysinfo` | 系统信息（CPU/内存/磁盘） |
| `remote_ping` | 连通性检测 |
| `remote_file` | 文件 list/read/write/copy/delete/info |
| `remote_app` | 启动/结束/搜索应用（exe 索引） |
| `remote_screenshot` | 截屏（保存本地 PNG + 直发图片给用户） |
| `remote_pull_file` | 拉取远程文件到本地并直发（图片直显，其余作附件；小文件单帧、大文件流式分块 + sha256 校验） |
| `remote_input` | 远程键盘输入：`text` 逐字符打字（支持中文），或 `keys` 敲击按键/组合键（ctrl+c、alt+f4、enter 等） |
| `remote_mouse` | 远程鼠标：click（left/right/middle、双击）/ move / scroll / drag（拖拽）。点击前自动把目标窗口切到前台（`activate=false` 可关闭），解决后台窗口首次点击被吞 |
| `remote_clipboard` | 远程剪贴板：`get` 读取远程复制的内容，`set` 写入远程剪贴板 |
| `remote_see` | 截屏 + 视觉模型识别：截图保存本地，调当前会话/指定 `model` 视觉模型返回屏幕元素名称、类型、像素坐标 |

所有工具支持可选 `device_id` 参数（多设备定向下发）。

> **坐标约定**：`remote_see` / `remote_screenshot` 返回的像素坐标就是 `remote_mouse` / `remote_input` 要用的坐标，直接照搬即可；多显示器偏移由 C 端自动换算，工具不会再返回 `offset_x/offset_y`，避免上层多算一次导致点偏。其中 `remote_see` → `remote_mouse` / `remote_input` 可组成「看屏幕 → 定位 → 点击/输入」的全自动操作闭环。

## 命令

- `/winremote`（旧 `/cherry` 仍兼容）—— 插件与在线设备状态
- `/devices` —— 列出在线设备
- `/screenshot` —— 直接截取 C 端屏幕并发图
- `/pull <远程路径>` —— 拉取 C 端文件并发图/发文件（路径含空格无需引号）
- `/see [描述]` —— 截取 C 端屏幕并调视觉模型识别画面元素与坐标（用于看屏幕操作电脑）

## 安装（B 端·云服务器）

1. **Docker 部署 AstrBot**，映射插件 WS 端口到宿主机：
   ```yaml
   # docker-compose.yml 片段
   ports:
     - "8765:8765"   # 插件 WebSocket 端口
   ```
2. 将本插件放入 AstrBot 的 `data/plugins/`（或从 GitHub 安装）。
3. 在 AstrBot 插件管理中启用「WinRemote」。
4. 配置（`_conf_schema.json`）：
   - `ws_port`：WS 服务端口（默认 8765）
   - `auth_token`：**必须与 C 端 config.yaml 完全一致**
   - `heartbeat_timeout`：心跳超时
   - `pull_threshold`：单帧拉取阈值（字节，默认 8MB，超过走流式分块）
   - `max_pull_size`：单次拉取大小上限（字节，默认 200MB）
   - `vision_use_current_model`：是否默认使用当前对话模型识别截图（默认开；当前模型需支持多模态）
   - `vision_caption_provider`：视觉转述模型提供商。当前对话模型不支持多模态时，用此模型把截图转述为含 UI 元素坐标的文本（WebUI 下拉选择或填提供商 id）
   - `vision_analyze_prompt`：识图提示词（默认已内置，要求输出可交互元素及像素坐标）
   - `vision_caption_prompt`：转述提示词（默认已内置，用于无多模态模型时转述屏幕布局与元素坐标）
5. AstrBot 全局配置建议：`computer_use_runtime = local`（让 skills 可执行；与本插件无关，但影响 skills/MCP 能力）。

> 视觉识别模型选择规则：`remote_see` / `/see` 默认先用当前对话模型识图；
> 若其不支持图像输入（调用抛错）且配置了 `vision_caption_provider`，会自动降级到转述模型；
> 关闭 `vision_use_current_model` 后则直接使用转述模型。

## 使用

- 直接对话（需 AstrBot 启用 Agent/Tool 模式）：`帮我截个图发给我`、`打开 C 盘某目录`、`让 C 电脑 ping 一下百度`、`把 C 电脑上的 xxx.zip 发给我`、**`看下远程屏幕，帮我点开记事本打一行字`**（`remote_see` → `remote_mouse` → `remote_input` 闭环）。
- 多设备：对话中指定设备名，或先 `/devices` 查看。

## 通信协议

见 [`docs/PROTOCOL.md`](docs/PROTOCOL.md)（与 winremote-app 共享）。

## 测试

仓库内置 B 端回归测试（stub AstrBot 环境，无需启动服务）：

```bash
python test_b_tools.py   # 10 个 FunctionTool 实例化/schema + remote_input/remote_mouse/remote_see 行为与视觉降级
```

全绿输出 `ALL PASS`。覆盖远程打字/按键路由、鼠标动作参数转发、`remote_see` 的截屏落盘、视觉调 `llm_generate` 传参以及旧版签名 `TypeError` 降级重试。

## 开发状态

- [x] M1 协议定稿
- [x] M2 插件骨架（WS 服务端 + FunctionTool）
- [x] M3 App 骨架联调
- [x] M4 功能扩展（file/app/screenshot + 审计）
- [x] M5 Agent 化（FunctionTool 工具集）
- [x] M6 安全加固（急停/多设备/防重复连接）
- [x] M7 文件拉取（remote_pull_file + /pull，流式分块 + sha256 校验）
- [x] M8 键鼠操控 + 视觉识别（remote_input / remote_mouse / remote_see 看图操作闭环）

## 作者

183kugua（原作 @littlewifeofsilverwolf）
