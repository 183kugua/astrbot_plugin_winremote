# SPDX-License-Identifier: AGPL-3.0-only
"""Cherry Remote —— AstrBot 远程操控连接器。

纯连接器：桥接 AstrBot（B端）与远程电脑上的 cherry-remote-app（C端）。
- 内嵌 aiohttp WebSocket 服务端，接受 C 端 App 主动外连（穿透 NAT）。
- 注册 FunctionTool，使 AstrBot Agent 可将用户需求转为远程指令下发。
- 回收执行结果回传 Agent 研判后，由 AstrBot 回复原会话。
"""

import asyncio
import base64
import json
import time
import types
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import FunctionTool, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageChain

try:
    from astrbot.core.agent.tool import ToolExecResult
except ImportError:  # pragma: no cover
    ToolExecResult = str  # type: ignore

from .ws_server import RemoteWsServer


def _get_plugin_data_dir() -> Path:
    """获取插件数据目录：data/plugin_data/cherry_remote/。"""
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path

    d = Path(get_astrbot_data_path()) / "plugin_data" / "cherry_remote"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_screenshot_image(data: dict) -> str:
    """把 C 端返回的 base64 截图解码并存到 B 端本地，返回文件路径。"""
    img_bytes = base64.b64decode(data["image"])
    shots = _get_plugin_data_dir() / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    fname = f"shot_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
    path = shots / fname
    path.write_bytes(img_bytes)
    return str(path)


def _persist_pulled(resp: dict) -> str:
    """把拉取结果落盘，返回本地路径（流式模式直接用落盘路径，单帧模式需写盘）。"""
    if resp.get("mode") == "stream":
        return resp["local_path"]
    pulls = _get_plugin_data_dir() / "pulls"
    pulls.mkdir(parents=True, exist_ok=True)
    fname = f"{int(time.time())}_{uuid.uuid4().hex[:6]}_{resp.get('name') or 'file'}"
    path = pulls / fname
    content = resp.get("content")
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(str(content), encoding="utf-8")
    return str(path)


def _pulled_chain(local_path: str, name: str, size_kb: int) -> list:
    """按文件类型构造发送链：图片直显，其余作为附件。"""
    ext = Path(local_path).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return [
            Comp.Image.fromFileSystem(local_path),
            Comp.Plain(f"{name}（{size_kb}KB）"),
        ]
    return [
        Comp.File(name=name, file=local_path),
        Comp.Plain(f"{name}（{size_kb}KB）"),
    ]


@dataclass
class RemoteExecTool(FunctionTool):
    """远程执行 shell 命令。"""

    name: str = "remote_exec"
    description: str = (
        "在远程电脑（C端）上执行一条 shell 命令并返回 stdout/stderr 与退出码。"
        "用于查看/操作远程电脑上的程序、文件与系统。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令。"},
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，默认 30。",
                    "default": 30,
                },
                "cwd": {"type": "string", "description": "工作目录，可选。"},
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定；仅一台时可不填）。",
                },
            },
            "required": ["command"],
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        timeout = int(kwargs.get("timeout") or 30)
        params = {"command": kwargs["command"], "timeout": timeout}
        if kwargs.get("cwd"):
            params["cwd"] = kwargs["cwd"]
        try:
            resp = await server.send_command(
                "exec", params, device_id=kwargs.get("device_id"), timeout=timeout + 10
            )
            return json.dumps(resp, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@dataclass
class RemoteSysInfoTool(FunctionTool):
    """获取远程电脑系统信息。"""

    name: str = "remote_sysinfo"
    description: str = (
        "获取远程电脑（C端）的系统信息，包括 CPU/内存/磁盘使用率、主机名、操作系统等。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        try:
            resp = await server.send_command(
                "sys", {}, device_id=kwargs.get("device_id"), timeout=30
            )
            return json.dumps(resp, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@dataclass
class RemotePingTool(FunctionTool):
    """探测远程电脑连通性。"""

    name: str = "remote_ping"
    description: str = "检测远程电脑（C端）是否在线，返回 pong。"
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        try:
            resp = await server.send_command(
                "ping", {}, device_id=kwargs.get("device_id"), timeout=15
            )
            return json.dumps(resp, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@dataclass
class RemoteFileTool(FunctionTool):
    """远程文件操作。"""

    name: str = "remote_file"
    description: str = (
        "对远程电脑（C端）进行文件操作。action 取值：list(列目录)、read(读文件)、"
        "write(写文件)、copy(复制)、delete(删除)、info(文件信息)。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "read", "write", "copy", "delete", "info"],
                    "description": "要执行的文件操作。",
                },
                "path": {"type": "string", "description": "源文件/目录路径。"},
                "dest": {"type": "string", "description": "目标路径（copy 时必填）。"},
                "content": {"type": "string", "description": "写入内容（write 时使用）。"},
                "recursive": {
                    "type": "boolean",
                    "description": "list 时是否递归列出，默认 false。",
                },
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
            "required": ["action", "path"],
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        params = {k: v for k, v in kwargs.items() if v is not None and k != "device_id"}
        try:
            resp = await server.send_command(
                "file", params, device_id=kwargs.get("device_id"), timeout=60
            )
            return json.dumps(resp, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@dataclass
class RemoteAppTool(FunctionTool):
    """远程启动/结束应用。"""

    name: str = "remote_app"
    description: str = (
        "在远程电脑（C端）上启动/结束/搜索应用程序。"
        "action：launch(启动)/terminate(结束)/search(在 exe 索引中搜索应用路径)。"
        "search 同时匹配 exe 文件名与产品名/文件说明（显示名，如“米哈游启动器”→HYP.exe），"
        "命中产品名时返回 matched_on=product 与 product 字段。若不确定应用名，先 search 查 exe 索引。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["launch", "terminate", "search"],
                    "description": "launch 启动 / terminate 结束 / search 搜索 exe 索引。",
                },
                "name": {
                    "type": "string",
                    "description": "应用名或完整路径（launch 用；terminate 时按进程名模糊匹配）。",
                },
                "query": {
                    "type": "string",
                    "description": "search 时的应用名关键字（不填则返回索引前 50 条）。",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "启动参数（launch 时可选）。",
                },
                "pid": {"type": "integer", "description": "按 PID 结束进程（terminate 时可选）。"},
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
            "required": ["action"],
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        params = {k: v for k, v in kwargs.items() if v is not None and k != "device_id"}
        try:
            resp = await server.send_command(
                "app", params, device_id=kwargs.get("device_id"), timeout=30
            )
            return json.dumps(resp, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@dataclass
class RemoteScreenshotTool(FunctionTool):
    """远程截屏。"""

    name: str = "remote_screenshot"
    description: str = (
        "截取远程电脑（C端）的完整屏幕（含所有显示器），保存为服务器本地 PNG 文件，"
        "并尝试直接把图片发送给用户。"
        "坐标约定：返回的截图与 remote_see 的坐标系完全一致——"
        "直接把截图里看到的像素坐标 (x, y) 交给 remote_mouse / remote_input 使用即可，"
        "不要加任何偏移量。"
        "reuse_seconds>0 时，若在此时长内刚截过图则直接复用上次画面（默认 5 秒），"
        "可避免连续截图闪烁；需要最新画面可传 0。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "reuse_seconds": {
                    "type": "number",
                    "description": "复用最近截图的秒数上限，默认 5；传 0 强制重新截屏。",
                },
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        params = {"reuse_seconds": kwargs.get("reuse_seconds", 5)}
        try:
            resp = await server.send_command(
                "screenshot", params, device_id=kwargs.get("device_id"), timeout=30
            )
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        if not resp.get("ok"):
            return json.dumps({"ok": False, "error": resp.get("error")}, ensure_ascii=False)

        data = resp["data"]
        try:
            path = _save_screenshot_image(data)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"保存截图失败: {e}"}, ensure_ascii=False)

        sent = False
        try:
            inner = getattr(context, "context", None)
            star_ctx = getattr(inner, "context", None)
            event = getattr(inner, "event", None)
            if star_ctx is not None and event is not None:
                chain = MessageChain().file_image(path)
                await star_ctx.send_message(event.unified_msg_origin, chain)
                sent = True
        except Exception as e:  # noqa: BLE001 —— 直发失败则回退为返回路径
            logger.warning(f"截图直接发送失败，改为返回路径: {e}")

        return json.dumps(
            {
                "ok": True,
                "sent_to_user": sent,
                "path": path,
                "width": data.get("width"),
                "height": data.get("height"),
                "size": data.get("size"),
                "reused": data.get("reused", False),
                "coord_hint": (
                    "截图坐标即点击坐标：直接用图中的 (x, y) 调 remote_mouse / remote_input，"
                    "不要加偏移量。"
                ),
            },
            ensure_ascii=False,
        )


@dataclass
class RemotePullFileTool(FunctionTool):
    """从远程电脑拉取文件到本地并直接发送。"""

    name: str = "remote_pull_file"
    description: str = (
        "从远程电脑（C端）拉取文件到本地并直接发送给用户（图片直显，其余作为附件发送）。"
        "支持任意类型与大小，自动选择单帧或流式传输。参数 path 为远程电脑上的文件完整路径。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "远程电脑上的文件完整路径，如 D:\\xx\\file.zip",
                },
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
            "required": ["path"],
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        try:
            resp = await server.pull_file(
                kwargs["path"], device_id=kwargs.get("device_id"), timeout=600
            )
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        if not resp.get("ok"):
            return json.dumps({"ok": False, "error": resp.get("error")}, ensure_ascii=False)
        try:
            local_path = _persist_pulled(resp)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"保存文件失败: {e}"}, ensure_ascii=False)

        sent = False
        try:
            inner = getattr(context, "context", None)
            star_ctx = getattr(inner, "context", None)
            event = getattr(inner, "event", None)
            if star_ctx is not None and event is not None:
                chain = MessageChain(
                    chain=_pulled_chain(
                        local_path, resp.get("name"), (resp.get("size") or 0) // 1024
                    )
                )
                await star_ctx.send_message(event.unified_msg_origin, chain)
                sent = True
        except Exception as e:  # noqa: BLE001 —— 直发失败则回退为返回路径
            logger.warning(f"文件直接发送失败，改为返回路径: {e}")

        return json.dumps(
            {
                "ok": True,
                "sent_to_user": sent,
                "mode": resp.get("mode"),
                "name": resp.get("name"),
                "size": resp.get("size"),
                "local_path": local_path,
            },
            ensure_ascii=False,
        )


@dataclass
class RemoteInputTool(FunctionTool):
    """远程键盘输入（文字/按键）。"""

    name: str = "remote_input"
    description: str = (
        "在远程电脑（C端）的当前活动窗口输入文字或敲击按键。"
        "text 用于输入文字（支持中文等 Unicode 字符）；keys 用于敲击按键或组合键，"
        "如 ['ctrl','c'] 复制、['enter'] 回车、['alt','f4'] 关闭窗口。"
        "支持按键名：字母/数字/enter/tab/esc/space/backspace/delete/insert/home/end/"
        "pageup/pagedown/上下左右/f1-f24/ctrl/shift/alt/win/num0-num9 等。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "要输入的文字（与 keys 二选一，支持中文）。",
                },
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要敲击的按键或组合键，如 ['ctrl','c']。",
                },
                "mode": {
                    "type": "string",
                    "enum": ["type", "paste"],
                    "description": "type=逐字符输入（默认）；paste=剪贴板粘贴（部分程序不支持 unicode 直输时用）。",
                },
                "interval": {
                    "type": "number",
                    "description": "字符间隔秒数（type 模式，默认 0.01）。",
                },
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        if not kwargs.get("text") and not kwargs.get("keys"):
            return json.dumps({"ok": False, "error": "text 与 keys 至少填一个"}, ensure_ascii=False)
        params = {k: v for k, v in kwargs.items() if v is not None and k != "device_id"}
        try:
            resp = await server.send_command(
                "input" if params.get("text") else "keys",
                params,
                device_id=kwargs.get("device_id"),
                timeout=60,
            )
            return json.dumps(resp, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@dataclass
class RemoteClipboardTool(FunctionTool):
    """远程剪贴板读写。"""

    name: str = "remote_clipboard"
    description: str = (
        "读写远程电脑（C端）的系统剪贴板文本。"
        "action=get 读取剪贴板内容（用于把远程复制的文字/路径/验证码取回来）；"
        "action=set 把文本写入远程剪贴板（常用于配合 remote_input 的 paste 模式，"
        "或在远程程序间传递长文本）。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "set"],
                    "description": "get=读取剪贴板，set=写入剪贴板，默认 get。",
                },
                "text": {
                    "type": "string",
                    "description": "action=set 时要写入的文本。",
                },
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
            "required": ["action"],
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        params = {k: v for k, v in kwargs.items() if v is not None and k != "device_id"}
        try:
            resp = await server.send_command(
                "clipboard", params, device_id=kwargs.get("device_id"), timeout=30
            )
            return json.dumps(resp, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@dataclass
class RemoteMouseTool(FunctionTool):
    """远程鼠标控制（点击/移动/滚动/拖拽）。"""

    name: str = "remote_mouse"
    description: str = (
        "控制远程电脑（C端）的鼠标：点击、移动、滚动、拖拽。"
        "坐标 x/y 为屏幕像素坐标（0,0 为左上角，可用 remote_see 或 remote_screenshot 的截图定位）。"
        "action：click=点击（默认）、move=移动悬停、scroll=滚轮、drag=拖拽。"
        "click 支持 button(left/right/middle) 与 clicks（双击传 2）；"
        "drag 需要 x/y（起点）与 x2/y2（终点），用于拖动窗口/文件等。"
        "坐标取自 remote_see / remote_screenshot 的截图，直接用截图像素即可，无需换算。"
        "默认会自动把点击位置的窗口切到前台再点击（Windows 会吞掉后台窗口的首次点击），"
        "返回的 activated_window 即被激活的窗口名；如确实要点后台窗口可传 activate=false。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["click", "move", "scroll", "drag"],
                    "description": "鼠标动作，默认 click。",
                },
                "x": {"type": "integer", "description": "目标 X 坐标（像素）。"},
                "y": {"type": "integer", "description": "目标 Y 坐标（像素）。"},
                "x2": {"type": "integer", "description": "drag 终点 X 坐标。"},
                "y2": {"type": "integer", "description": "drag 终点 Y 坐标。"},
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "鼠标键，默认 left。",
                },
                "clicks": {"type": "integer", "description": "点击次数（双击传 2），默认 1。"},
                "dy": {"type": "integer", "description": "scroll 滚动格数，正数向上、负数向下。"},
                "activate": {
                    "type": "boolean",
                    "description": "点击前若目标窗口不在前台则先激活它，默认 true。",
                },
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
            "required": ["action"],
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        params = {k: v for k, v in kwargs.items() if v is not None and k != "device_id"}
        try:
            resp = await server.send_command(
                "mouse", params, device_id=kwargs.get("device_id"), timeout=60
            )
            return json.dumps(resp, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


# 统一坐标说明：截图坐标 == 点击坐标，C 端会自动处理多屏偏移。
# 这里刻意不回传 offset_x/offset_y——一旦回传，模型容易自行做一次多余换算而点偏。
_COORD_HINT = (
    "下列坐标可直接用于 remote_mouse / remote_input："
    "analysis 中给出的 (x, y) 就是截图像素坐标，照搬即可，"
    "不要加偏移量、不要按屏幕尺寸缩放（多屏偏移由 C 端自动处理）。"
)

_SEE_ANALYZE_PROMPT = "你是一个屏幕识别助手。用户会给你一张电脑屏幕截图，请按要求识别并回答。你必须识别出截图中所有可交互的 UI 元素（按钮、输入框、图标、链接、菜单、复选框、滚动条、窗口、标签页等），并给出每个元素的像素坐标位置，以便程序可以根据坐标进行鼠标点击、键盘输入等操作。\n输出要求：\n1. 用以下格式逐条列出元素（每行一个）：\n   元素名 | 类型 | x,y,width,height\n   类型取：button/input/icon/link/text/window/menu/checkbox/scrollbar/tab 等。\n2. 坐标必须是截图内的像素坐标，左上角为原点，x 向右增大、y 向下增大，单位像素。\n3. 只列出截图里真实存在的元素，不要编造。\n4. 若用户提出具体指令（如『找到登录按钮』），先回答目标元素，再补充其他可交互元素。"

_SEE_CAPTION_PROMPT = "你是一个屏幕转述助手。用户会给你一张电脑屏幕截图，请把屏幕内容完整转述成文字，让一个看不到图片的 AI 也能据此理解屏幕布局并操作电脑。\n转述要求：\n1. 先用一段话概括整体界面：操作系统、当前窗口/应用、主要区域划分。\n2. 然后逐条列出所有可交互 UI 元素，每行一个，格式：\n   元素名 | 类型 | x,y,width,height | 用途描述\n   类型取：button/input/icon/link/text/window/menu/checkbox/scrollbar/tab 等。\n3. 坐标必须是截图内的像素坐标，左上角为原点，x 向右增大、y 向下增大，单位像素。\n4. 额外说明：当前焦点所在、可输入位置、明显的操作入口。\n只描述截图里真实存在的内容，不要编造。全程使用中文。"


@dataclass
class RemoteSeeTool(FunctionTool):
    """远程截屏 + 视觉模型识别（看屏幕、定位元素）。

    模型选择规则（按插件配置）：
    - vision_use_current_model=True（默认）：优先用当前会话模型识别截图；
      若该模型不支持多模态（识别抛错）且配置了 vision_caption_provider，自动降级到转述模型。
    - vision_use_current_model=False：跳过当前模型，直接使用配置的转述模型
      （vision_caption_provider），否则报错提示配置。
    - 工具参数 model 可覆盖具体模型名。
    """

    name: str = "remote_see"
    description: str = (
        "截取远程电脑（C端）屏幕并调用视觉模型识别内容，返回屏幕元素"
        "（窗口、按钮、输入框、图标、文本等）的名称、类型与像素坐标。"
        "用途：先 remote_see 查看远程屏幕/定位元素坐标，再配合 remote_mouse 点击、"
        "remote_input 输入，实现看图操作电脑。返回 JSON 含 elements 列表"
        "（label/type/x/y/width/height，坐标为像素）与截图保存路径。"
        "识别默认使用当前对话模型；若其不支持图像，将按插件配置自动降级到视觉转述模型。"
        "返回的像素坐标可直接交给 remote_mouse / remote_input 使用，"
        "不要做任何偏移或缩放换算（多屏偏移由 C 端自动处理）。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "可选：识别指令，如『找到登录按钮并给出坐标』。默认描述整屏。",
                },
                "model": {
                    "type": "string",
                    "description": "可选：覆盖视觉模型名（默认按插件配置选择模型，见配置项 vision_*）。",
                },
                "device_id": {
                    "type": "string",
                    "description": "目标设备 id（多设备在线时指定）。",
                },
            },
        }
    )

    async def call(self, context: Any, **kwargs) -> ToolExecResult:
        server: RemoteWsServer | None = getattr(self, "_server", None)
        if server is None:
            return json.dumps({"ok": False, "error": "连接器尚未初始化"}, ensure_ascii=False)
        # 1) 截屏
        try:
            resp = await server.send_command(
                "screenshot", {}, device_id=kwargs.get("device_id"), timeout=30
            )
        except Exception as e:
            return json.dumps({"ok": False, "error": f"截屏失败: {e}"}, ensure_ascii=False)
        if not resp.get("ok"):
            return json.dumps({"ok": False, "error": resp.get("error")}, ensure_ascii=False)
        data = resp["data"]
        try:
            path = _save_screenshot_image(data)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"保存截图失败: {e}"}, ensure_ascii=False)

        # 2) 解析插件配置
        cfg: dict = getattr(self, "_config", None) or {}
        use_current = bool(cfg.get("vision_use_current_model", True))
        caption_provider = str(cfg.get("vision_caption_provider", "") or "").strip() or None
        analyze_sys = str(cfg.get("vision_analyze_prompt", "") or "").strip() or None
        caption_sys = str(cfg.get("vision_caption_prompt", "") or "").strip() or None

        # 3) 视觉模型识别（当前模型 -> 失败降级转述模型 / 或直接转述模型）
        prompt = kwargs.get("prompt") or (
            "描述屏幕上的主要内容，并列出所有可交互元素（按钮/输入框/图标/链接等）及其像素坐标。"
        )
        try:
            analysis = await self._vision_analyze(
                context,
                path,
                prompt,
                kwargs.get("model"),
                use_current_model=use_current,
                caption_provider=caption_provider,
                analyze_system=analyze_sys,
                caption_system=caption_sys,
            )
        except Exception as e:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"视觉识别失败: {e}",
                    "screenshot_path": path,
                    "hint": (
                        "当前会话模型可能不支持图像输入。可在插件配置中开启"
                        "『默认使用当前对话模型识别截图』，或配置『视觉转述模型"
                        "（vision_caption_provider）』用于无多模态模型时的自动降级；"
                        "也可在本工具调用时传 model 参数指定支持视觉的模型。"
                    ),
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "ok": True,
                "analysis": analysis,
                "screenshot_path": path,
                "width": data.get("width"),
                "height": data.get("height"),
                "coord_hint": _COORD_HINT,
            },
            ensure_ascii=False,
        )

    async def _vision_analyze(
        self,
        context: Any,
        image_path: str,
        prompt: str,
        model: str | None,
        use_current_model: bool = True,
        caption_provider: str | None = None,
        analyze_system: str | None = None,
        caption_system: str | None = None,
    ) -> str:
        """调用 LLM 视觉能力分析截图，返回模型文本。

        - use_current_model=True：优先当前会话模型 + 识图提示词；
          若调用抛错（如模型不支持多模态）且给出 caption_provider，则降级到
          caption_provider + 转述提示词。
        - use_current_model=False：跳过当前模型，直接使用 caption_provider + 转述提示词。
        """
        inner = getattr(context, "context", None)
        star_ctx = getattr(inner, "context", None)
        event = getattr(inner, "event", None)
        if star_ctx is None or not hasattr(star_ctx, "llm_generate"):
            raise RuntimeError("无法获取 AstrBot LLM 上下文（llm_generate 不可用）")

        analyze_system = analyze_system or _SEE_ANALYZE_PROMPT
        caption_system = caption_system or _SEE_CAPTION_PROMPT

        async def _generate(provider_id: str, system: str) -> str:
            kw: dict = {}
            if model:
                kw["model"] = model
            try:
                resp = await star_ctx.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                    system_prompt=system,
                    image_urls=[image_path],
                    **kw,
                )
            except TypeError:
                # 旧版 AstrBot 签名差异：去掉不兼容参数重试
                resp = await star_ctx.llm_generate(
                    chat_provider_id=provider_id, prompt=prompt, image_urls=[image_path], **kw
                )
            text = getattr(resp, "completion_text", None) or getattr(resp, "result_chain", None)
            if text is None:
                raise RuntimeError("视觉模型未返回文本")
            return text

        async def _current_provider() -> str | None:
            umo = getattr(event, "unified_msg_origin", None) if event else None
            if umo and hasattr(star_ctx, "get_current_chat_provider_id"):
                try:
                    return await star_ctx.get_current_chat_provider_id(umo=umo)
                except Exception:
                    pass
            # 退化为默认 provider（同步 API 兜底）
            pm = getattr(star_ctx, "provider_manager", None)
            if pm and hasattr(pm, "get_using_provider"):
                try:
                    return getattr(pm.get_using_provider(), "provider_id", None)
                except Exception:
                    pass
            return None

        cur_provider = await _current_provider()
        last_err: Exception | None = None

        if use_current_model and cur_provider:
            try:
                return await _generate(cur_provider, analyze_system)
            except Exception as e:
                last_err = e
                # 当前模型不支持多模态 → 有转述模型则降级
                if not caption_provider:
                    raise

        if caption_provider:
            # 降级 或（use_current_model=False 时）直接使用转述模型
            try:
                return await _generate(caption_provider, caption_system)
            except Exception as e:
                last_err = e
                raise RuntimeError(
                    f"视觉转述模型（{caption_provider}）识别失败: {e}"
                ) from e

        if not use_current_model:
            raise RuntimeError(
                "已关闭『默认使用当前对话模型识别截图』，且未配置视觉转述模型"
                "（vision_caption_provider）。请到插件配置中开启开关或指定转述模型。"
            )
        if not cur_provider:
            raise RuntimeError("无法确定当前 LLM provider")
        if last_err is not None:
            raise last_err
        raise RuntimeError("视觉识别失败")

@register(
    "astrbot_plugin_cherry_remote",
    "littlewifeofsilverwolf",
    "远程操控连接器：桥接 AstrBot 与远程电脑 App",
    "1.4.0",
)
class CherryRemote(Star):
    """Cherry Remote —— 远程操控连接器。

    桥接 AstrBot 与远程电脑上的 cherry-remote-app：
    - 建立 B 端 WebSocket 服务，接受 C 端 App 主动外连（穿透 NAT）
    - 注册 FunctionTool，使 AstrBot Agent 可将用户需求转为远程指令下发
    - 回收执行结果回传 Agent 研判，最终回复发回原会话
    """

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.server: RemoteWsServer | None = None
        self._server_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """启动 WebSocket 服务端并注册 FunctionTool。"""
        port = int(self.config.get("ws_port", 8765))
        token = str(self.config.get("auth_token", ""))
        heartbeat_timeout = int(self.config.get("heartbeat_timeout", 60))

        self.server = RemoteWsServer(
            port=port,
            token=token,
            heartbeat_timeout=heartbeat_timeout,
            pull_threshold=int(self.config.get("pull_threshold", 8 * 1024 * 1024)),
            max_pull_size=int(self.config.get("max_pull_size", 200 * 1024 * 1024)),
            pull_dir=str(_get_plugin_data_dir() / "pulls"),
        )
        self._server_task = asyncio.create_task(self.server.start())

        tools = self._build_tools()
        if tools:
            self.context.add_llm_tools(*tools)
        logger.info("Cherry Remote 初始化完成。")

    def _build_tools(self) -> list[FunctionTool]:
        if self.server is None:
            return []
        built: list[FunctionTool] = []
        for tool_cls in (
            RemoteExecTool,
            RemoteSysInfoTool,
            RemotePingTool,
            RemoteFileTool,
            RemoteAppTool,
            RemoteScreenshotTool,
            RemotePullFileTool,
            RemoteInputTool,
            RemoteMouseTool,
            RemoteClipboardTool,
            RemoteSeeTool,
        ):
            tool = tool_cls()
            tool._server = self.server  # type: ignore[attr-defined]
            tool._config = self.config  # type: ignore[attr-defined]
            built.append(tool)
        return built

    @filter.command("cherry")
    async def cherry(self, event: AstrMessageEvent):
        """Cherry Remote 状态查询。发送 `/cherry` 检查插件与设备状态。"""
        if self.server is None:
            yield event.plain_result("Cherry Remote 尚未初始化。")
            return
        devices = self.server.device_summary()
        if not devices:
            yield event.plain_result(
                "Cherry Remote 已就绪，但暂无远程设备在线。请先启动 C 端 cherry-remote-app 并接入。"
            )
            return
        lines = [f"- {d['device_id']}（session {d['session_id'][:8]}）" for d in devices]
        yield event.plain_result("Cherry Remote 已就绪，在线设备：\n" + "\n".join(lines))

    @filter.command("devices")
    async def devices(self, event: AstrMessageEvent):
        """列出当前在线设备。"""
        if self.server is None:
            yield event.plain_result("Cherry Remote 尚未初始化。")
            return
        devices = self.server.device_summary()
        if not devices:
            yield event.plain_result("暂无在线设备。")
            return
        lines = [f"- {d['device_id']}（session {d['session_id'][:8]}）" for d in devices]
        yield event.plain_result("在线设备：\n" + "\n".join(lines))

    @filter.command("screenshot")
    async def screenshot(self, event: AstrMessageEvent):
        """截取 C 端完整屏幕并直接以图片发送。"""
        if self.server is None:
            yield event.plain_result("Cherry Remote 尚未初始化。")
            return
        try:
            resp = await self.server.send_command("screenshot", {}, timeout=30)
        except Exception as e:
            yield event.plain_result(f"截屏失败: {e}")
            return
        if not resp.get("ok"):
            yield event.plain_result(f"截屏失败: {resp.get('error')}")
            return
        data = resp["data"]
        try:
            path = _save_screenshot_image(data)
        except Exception as e:
            yield event.plain_result(f"截屏成功但保存失败: {e}")
            return
        size_kb = (data.get("size") or 0) // 1024
        yield event.chain_result(
            [
                Comp.Image.fromFileSystem(path),
                Comp.Plain(f"截图 {data.get('width')}x{data.get('height')}（{size_kb}KB）"),
            ]
        )

    @filter.command("see")
    async def see(self, event: AstrMessageEvent):
        """截取 C 端屏幕并调视觉模型识别画面元素与坐标。用法：/see [描述]"""
        if self.server is None:
            yield event.plain_result("Cherry Remote 尚未初始化。")
            return
        # 可选描述，去掉命令前缀
        msg = event.get_message_str().strip()
        parts = msg.split(maxsplit=1)
        prompt = parts[1].strip().strip('"') if len(parts) > 1 else None
        # 1) 截屏
        try:
            resp = await self.server.send_command("screenshot", {}, timeout=30)
        except Exception as e:
            yield event.plain_result(f"截屏失败: {e}")
            return
        if not resp.get("ok"):
            yield event.plain_result(f"截屏失败: {resp.get('error')}")
            return
        data = resp["data"]
        try:
            path = _save_screenshot_image(data)
        except Exception as e:
            yield event.plain_result(f"截屏成功但保存失败: {e}")
            return
        # 2) 复用 remote_see 工具的视觉分析（self.context 即 Star 的 Context，支持 llm_generate）
        bytelist = [Comp.Image.fromFileSystem(path)]
        try:
            ctx_wrapper = types.SimpleNamespace(
                context=types.SimpleNamespace(context=self.context, event=event)
            )
            model = None
            if prompt and prompt.startswith("model="):
                model = prompt.split("=", 1)[1].strip() or None
                prompt = None
            analysis = await RemoteSeeTool()._vision_analyze(
                ctx_wrapper,
                path,
                prompt,
                model,
                use_current_model=bool(self.config.get("vision_use_current_model", True)),
                caption_provider=str(
                    self.config.get("vision_caption_provider", "") or ""
                ).strip()
                or None,
                analyze_system=str(
                    self.config.get("vision_analyze_prompt", "") or ""
                ).strip()
                or None,
                caption_system=str(
                    self.config.get("vision_caption_prompt", "") or ""
                ).strip()
                or None,
            )
        except Exception as e:
            msg = (
                f"\n视觉识别失败: {e}\n"
                "提示：可在插件配置中开启『默认使用当前对话模型识别截图』，"
                "或配置『视觉转述模型（vision_caption_provider）』用于无多模态模型时的降级。"
            )
            yield event.chain_result(bytelist + [Comp.Plain(msg)])
            return
        size_kb = (data.get("size") or 0) // 1024
        yield event.chain_result(
            bytelist
            + [
                Comp.Plain(
                    f"识别结果：\n{analysis}\n"
                    f"截图 {data.get('width')}x{data.get('height')}（{size_kb}KB）"
                )
            ]
        )

    @filter.command("pull")
    async def pull(self, event: AstrMessageEvent):
        """从 C 端拉取文件并直接发送。用法：/pull <远程文件路径>（路径含空格无需引号）"""
        if self.server is None:
            yield event.plain_result("Cherry Remote 尚未初始化。")
            return
        msg = event.get_message_str().strip()
        parts = msg.split(maxsplit=1)
        path = parts[1].strip().strip('\"') if len(parts) > 1 else ""
        if not path:
            yield event.plain_result(
                "用法：/pull <远程文件路径>，例如 /pull D:\\temp\\report.pdf"
            )
            return
        try:
            resp = await self.server.pull_file(path, timeout=600)
        except Exception as e:
            yield event.plain_result(f"拉取失败: {e}")
            return
        if not resp.get("ok"):
            yield event.plain_result(f"拉取失败: {resp.get('error')}")
            return
        try:
            local_path = _persist_pulled(resp)
        except Exception as e:
            yield event.plain_result(f"文件已拉到本地但保存失败: {e}")
            return
        size_kb = (resp.get("size") or 0) // 1024
        yield event.chain_result(_pulled_chain(local_path, resp.get("name"), size_kb))

    async def terminate(self) -> None:
        """插件卸载/停用时：停止服务端，释放资源。"""
        if self.server:
            await self.server.stop()
        logger.info("Cherry Remote 连接器已停止。")
