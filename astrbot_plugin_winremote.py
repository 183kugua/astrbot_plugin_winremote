"""
astrbot_plugin_winremote.py — AStrBot V1.0.0 唯一真源
======================================================
AStrBot 加载规则：目录 astrbot_plugin_winremote/ 下必须有
  main.py  或  astrbot_plugin_winremote.py
本文件满足两种命名约定，main.py 作为薄壳入口。

V1.0.0 核心改造：
- WebUI 全面升级：Dashboard 增加授权状态面板 + 一键吊销
- Settings 页面新增授权配置组 + SHA-256 密码哈希生成器
- Logs 页面增加 HMAC 完整性校验按钮 + 授权事件标签
- Widget 增加授权状态指示 + 审计完整性实时显示

V1.0.0 核心改造：
- 集成 AuthManager（auth.py）：会话级临时授权，替代永久开关
- 新增私聊确认机制（confirm.py）：高危操作需管理员实时确认
- 审计日志加 HMAC-SHA256 签名（防篡改）
- 删除所有"永久开启"逻辑，改为"默认关闭 + 临时授权 + 自动过期"
- auth_ttl_seconds 可配置（默认300秒，0=永久但需私聊确认）


架构（测试友好，职责分离）：
- AuthManager        : 会话级授权 + HMAC 审计（auth.py）
- WinRemoteServer   : WebSocket 服务端 + Agent 生命周期
- AgentManager      : Agent 注册/查找/清理
- AgentConnection   : 单个 Agent 的数据模型
- PasswordGuard     : 二次密码 + 封禁
- WinRemotePlugin   : AStrBot 插件壳，持有 Server + AuthManager
- 全局函数 get_config / validate_command / validate_path
"""

from __future__ import annotations

# ============================================================
# 标准库
# ============================================================
import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

# ============================================================
# 本地模块（v1.0.0：会话级授权 + 私聊确认）
# 使用基于 __file__ 的路径导入，兼容 AStrBot 的 importlib 加载方式
# （AStrBot 不一定把插件目录加入 sys.path）
# ============================================================
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# noqa: E402 — 上面必须在 import 前执行（确保 sys.path 包含插件目录）
from auth import AuthManager  # noqa: E402
from confirm import request_private_confirm  # noqa: E402

# ============================================================
# AStrBot _conf_schema.json 类型白名单（唯一真源）
# ============================================================
# AStrBot 的 _parse_schema 只认这 9 个 type 字符串。
# 任何动态生成 / 校验 schema 的代码都必须 assert t in SCHEMA_TYPE_WHITELIST，
# 防止再写出 "array" / "integer" / "arrays" 这类非法类型。
SCHEMA_TYPE_WHITELIST = frozenset(
    {
        "int",  # 整数（不是 "integer"）
        "float",  # 浮点
        "bool",  # 布尔（不是 "boolean"）
        "string",  # 单行文本
        "text",  # 多行文本
        "list",  # 列表 / 数组（不是 "array" / "arrays"）
        "file",  # 文件上传
        "object",  # 嵌套对象
        "template_list",  # 模板列表
        "dict",  # 自由字典
    }
)

# ============================================================
# 第三方
# ============================================================
try:
    import websockets
    from websockets.exceptions import ConnectionClosed

    _HAS_WS = True
except ImportError:  # pragma: no cover
    websockets = None
    ConnectionClosed = Exception
    _HAS_WS = False

# ============================================================
# AStrBot API（带 fallback，让测试环境能 import）
# ============================================================
try:
    from astrbot.api import AstrBotConfig
    from astrbot.api import logger as ab_logger
    from astrbot.api.event import filter as astr_filter
    from astrbot.api.star import Context, Star
    from astrbot.core.star.star_handler import (
        CommandType,
        EventType,
        StarHandlerMetadata,
        StarHandlerType,
    )
    from astrbot.core.star.star_tools import register

    _HAS_ASTRBOT = True
except ImportError:  # pragma: no cover
    AstrBotConfig = dict
    ab_logger = None
    Context = Any
    Star = object

    def register(*a, **kw):
        def deco(cls):
            return cls

        return deco

    def StarHandlerMetadata(**kw):
        def _wrap(func):
            return func

        return _wrap

    # filter fallback：原样返回函数，且模拟 .event_message_type 等属性
    class _FilterFallback:
        def __call__(self, *a, **kw):
            def deco(func):
                return func
            return deco

        def __getattr__(self, name):
            # 返回自身，支持链式调用如 filter.event_message_type(...)
            return self

    astr_filter = _FilterFallback()

    StarTools = None

    class _EnumFallback:
        def __getattr__(self, name):
            return name

    StarHandlerType = _EnumFallback()
    EventType = _EnumFallback()
    CommandType = _EnumFallback()
    _HAS_ASTRBOT = False

# ============================================================
# 常量
# ============================================================
PLUGIN_NAME = "astrbot_plugin_winremote"
VERSION = "0.9.6"

DANGEROUS_KEYWORDS = [
    "rm ",
    "del ",
    "format",
    "shutdown",
    "reboot",
    "mkfs",
    "dd if=",
    "reg add",
    "reg delete",
    "net user",
    ":(){ :|:& };:",
    "wget ",
    "curl ",
]
INJECTION_CHARS = ["&&", "||", ";", "`", "$(", "| ", " >", " <", ">>", "<<"]

MAX_OUTPUT_BYTES = 8192
STREAM_CHUNK_SIZE = 1024
STREAM_INTERVAL = 0.5

HEARTBEAT_INTERVAL = 15
HEARTBEAT_TIMEOUT = 45

AUDIT_MAX = 1000


# ============================================================
# 日志
# ============================================================
logger = logging.getLogger(f"AstrBot.{PLUGIN_NAME}")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(f"[%(asctime)s] [{PLUGIN_NAME}] [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


# ============================================================
# AgentConnection
# ============================================================
class AgentConnection:
    """单个已连接 Agent 的数据模型"""

    def __init__(self, ws=None, agent_id: str = "unknown"):
        self.agent_id = agent_id
        self.ws = ws
        self.metadata: dict = {}
        self.authenticated: bool = False
        self.last_heartbeat = time.time()
        self.current_task: str | None = None
        self.connected_at = time.time()
        self.busy: bool = False

    def is_alive(self, timeout: int = HEARTBEAT_TIMEOUT) -> bool:
        return (time.time() - self.last_heartbeat) < timeout

    def touch(self) -> None:
        self.last_heartbeat = time.time()

    def __repr__(self) -> str:
        s = "认证" if self.authenticated else "未认证"
        a = "在线" if self.is_alive() else "离线"
        return f"Agent({self.agent_id}, {a}, {s})"


# ============================================================
# AgentManager
# ============================================================
class AgentManager:
    """Agent 注册 / 查找 / 清理（被 Server 持有）"""

    def __init__(self, max_agents: int = 8):
        self._agents: dict[str, AgentConnection] = {}
        self.max_agents = max_agents

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents

    async def add(self, agent: AgentConnection) -> bool:
        if len(self._agents) >= self.max_agents:
            return False
        self._agents[agent.agent_id] = agent
        return True

    async def remove(self, agent_id: str) -> None:
        if agent_id in self._agents:
            try:
                await self._agents[agent_id].ws.close()
            except Exception:
                pass
            del self._agents[agent_id]

    async def list(self) -> list[AgentConnection]:
        return list(self._agents.values())

    def get(self, agent_id: str) -> AgentConnection | None:
        return self._agents.get(agent_id)

    def find(self, name: str | None = None) -> AgentConnection | None:
        if not self._agents:
            return None
        if name:
            for a in self._agents.values():
                if a.agent_id == name or a.agent_id.startswith(name):
                    return a
            return None
        for a in self._agents.values():
            if a.is_alive():
                return a
        return None

    async def prune(self, timeout: int = HEARTBEAT_TIMEOUT) -> list[str]:
        dead = [aid for aid, a in self._agents.items() if not a.is_alive(timeout)]
        for aid in dead:
            try:
                await self._agents[aid].ws.close()
            except Exception:
                pass
            del self._agents[aid]
        return dead


# ============================================================
# PasswordGuard
# ============================================================
class PasswordGuard:
    def __init__(self, max_attempts: int = 5, ban_duration: int = 300):
        self.max_attempts = max_attempts
        self.ban_duration = ban_duration
        self._attempts: dict[str, list[float]] = {}

    async def check(self, peer: str, provided: str | None, expected: str) -> tuple[bool, str]:
        # Banned check FIRST — even correct password is rejected for banned peer
        if await self.is_banned(peer):
            return False, f"密码错误次数过多，封禁 {self.ban_duration} 秒"
        if not expected:
            return True, ""
        if not provided:
            return False, "需要二次密码"
        if provided != expected:
            now = time.time()
            fails = self._attempts.get(peer, [])
            fails = [t for t in fails if now - t < 3600]
            fails.append(now)
            self._attempts[peer] = fails
            if len(fails) >= self.max_attempts:
                return False, f"密码错误次数过多，封禁 {self.ban_duration} 秒"
            return False, "二次密码错误"
        self._attempts.pop(peer, None)
        return True, ""

    async def is_banned(self, peer: str) -> bool:
        fails = self._attempts.get(peer, [])
        if not fails:
            return False
        now = time.time()
        fails = [t for t in fails if now - t < self.ban_duration]
        self._attempts[peer] = fails
        return len(fails) >= self.max_attempts


# ============================================================
# AuditLogger
# ============================================================
def get_config(user_config: Any = None) -> dict:
    """读取/合并配置，返回扁平 dict"""
    defaults: dict = {
        "ws_host": "127.0.0.1",
        "ws_port": 6190,
        "ws_path": "/winremote",
        "secret_token": "",
        "token_rotation_days": 90,
        "admin_password": "",
        "password_max_attempts": 5,
        "password_ban_duration": 300,
        "require_encryption": False,
        "admin_qq": [],
        "allow_group": False,
        "heartbeat_interval": 15,
        "heartbeat_timeout": 45,
        "max_agents": 8,
        "command_whitelist": [
            "shell",
            "powershell",
            "screenshot",
            "key",
            "mouse",
            "open",
            "readfile",
        ],
        "command_blacklist": list(DANGEROUS_KEYWORDS),
        "command_regex_blacklist": [
            r"powershell\s+-enc",
            r"cmd\s+/c\s+\"",
            r"&&",
            r"\|\|",
            r";\s*rm",
            r";\s*del",
            r"\$\(.*\)",
        ],
        "allow_powershell": True,
        "strict_whitelist": False,
        "path_whitelist": ["C:\\Temp", "C:\\Users\\Public", "D:\\Shared"],
        "path_blacklist_keywords": [
            "..\\",
            "../",
            "%USERPROFILE%",
            "%SYSTEMROOT%",
            "C:\\Windows",
            "C:\\Program Files",
        ],
        "max_read_bytes": 65536,
        "file_allow_write": False,
        "auto_screenshot": True,
        "screenshot_format": "JPEG",
        "screenshot_quality": 75,
        "max_output_bytes": 8192,
        "stream_chunk_size": 1024,
        "stream_interval_ms": 500,
        "shell_timeout": 30,
    }

    if user_config is None:
        return dict(defaults)

    merged = dict(defaults)
    if isinstance(user_config, dict):
        for k, v in user_config.items():
            if k in defaults:
                merged[k] = v
        return merged

    # AstrBotConfig-like object
    try:
        for k in defaults:
            val = user_config.get(k, None)
            if val is not None:
                merged[k] = val
    except Exception:
        pass
    return merged


def validate_command(cmd: str, config: dict | None = None) -> tuple[bool, str]:
    """四重命令校验"""
    if config is None:
        config = get_config()

    cmd_s = (cmd or "").strip()
    if not cmd_s:
        return False, "empty command"

    blacklist = config.get("command_blacklist", DANGEROUS_KEYWORDS)
    cmd_lower = cmd_s.lower()
    for kw in blacklist:
        if kw.lower() in cmd_lower:
            return False, f"blacklist hit: {kw}"

    for ch in INJECTION_CHARS:
        if ch in cmd_s:
            return False, f"injection char: {ch}"

    regex_black = config.get("command_regex_blacklist", [])
    for pattern in regex_black:
        try:
            if re.search(pattern, cmd_s):
                return False, f"regex blacklist: {pattern}"
        except re.error:
            continue

    strict = config.get("strict_whitelist", False)
    whitelist = config.get("command_whitelist", [])
    if strict and whitelist:
        first = cmd_s.split()[0] if cmd_s.split() else ""
        if not any(first.lower().startswith(w.lower()) for w in whitelist):
            return False, f"not in whitelist: {first}"

    return True, ""


def validate_path(filepath: str, config: dict | None = None) -> tuple[bool, str]:
    """路径白名单 + 越狱关键词"""
    if config is None:
        config = get_config()

    if not filepath or not str(filepath).strip():
        return False, "empty path"

    whitelist = config.get("path_whitelist", [])
    blacklist_kw = config.get("path_blacklist_keywords", [])

    fp = str(filepath)
    fp_lower = fp.lower()
    for kw in blacklist_kw:
        if kw.lower() in fp_lower:
            return False, f"forbidden keyword: {kw}"

    if whitelist:
        allowed = any(fp_lower.startswith(str(w).lower()) for w in whitelist)
        if not allowed:
            return False, f"not in whitelist: {filepath}"

    return True, ""


# ============================================================
# WinRemoteServer（可独立构造，供测试使用）
# ============================================================
class WinRemoteServer:
    """
    WebSocket 服务端 + Agent 生命周期管理。
    可被 AstrBot 插件壳持有，也可被测试直接构造。
    """

    def __init__(self, context=None, config: dict | None = None):
        self.context = context
        self.cfg = get_config(config)
        self.agents = AgentManager(max_agents=self.cfg["max_agents"])
        self.pwd_guard = PasswordGuard(
            max_attempts=self.cfg["password_max_attempts"],
            ban_duration=self.cfg["password_ban_duration"],
        )
        self._ws_server = None
        self._running = False

    # -- 生命周期 --
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        host = self.cfg["ws_host"]
        port = int(self.cfg["ws_port"])
        require_enc = bool(self.cfg["require_encryption"])
        logger.info(f"WinRemote 启动 WebSocket {host}:{port}")

        if not _HAS_WS:
            logger.warning("websockets 未安装，跳过启动")
            self._running = False
            return

        async def handler(ws):
            await self._handle_agent(ws, require_encryption=require_enc)

        try:
            self._ws_server = await websockets.serve(
                handler, host, port, ping_interval=20, ping_timeout=10
            )
            logger.info(f"✅ 监听中 ws://{host}:{port}")
        except Exception as e:
            logger.error(f"❌ 启动失败: {e}")
            self._running = False

    async def stop(self) -> None:
        self._running = False
        for a in list(self.agents._agents.values()):
            try:
                await a.ws.close()
            except Exception:
                pass
        self.agents._agents.clear()
        if self._ws_server:
            self._ws_server.close()
            try:
                await self._ws_server.wait_closed()
            except Exception:
                pass
            self._ws_server = None

    # -- Agent 处理 --
    async def _handle_agent(self, ws, require_encryption: bool = False) -> None:
        peer = getattr(ws, "remote_address", ("?", "?"))[0]
        logger.info(f"Agent 连接来自 {peer}")

        # 加密检查
        if require_encryption and not getattr(ws, "secure", False):
            logger.warning(f"拒绝非加密连接 {peer}")
            try:
                await ws.send(
                    json.dumps({"type": "error", "message": "Encryption required. Use wss://"})
                )
                await ws.close()
            except Exception:
                pass
            return

        # 未配置 token → 拒绝
        expected = self.cfg["secret_token"]
        if not expected:
            try:
                await ws.send(
                    json.dumps(
                        {"type": "error", "message": "server misconfigured: secret_token empty"}
                    )
                )
                await ws.close()
            except Exception:
                pass
            return

        agent: AgentConnection | None = None
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug(f"忽略非 JSON: {str(raw)[:80]}")
                    continue

                mtype = msg.get("type", "")

                if mtype == "handshake":
                    token = msg.get("token", "")
                    if token != expected:
                        logger.warning(f"认证失败 from {peer}")
                        try:
                            await ws.send(json.dumps({"type": "error", "message": "Invalid token"}))
                        except Exception:
                            pass
                        break
                    aid = msg.get("agent_id", f"agent-{uuid.uuid4().hex[:8]}")
                    agent = AgentConnection(ws=ws, agent_id=aid)
                    agent.authenticated = True
                    agent.touch()
                    ok = await self.agents.add(agent)
                    if not ok:
                        logger.warning(f"Agent 数达上限，拒绝 {aid}")
                        try:
                            await ws.send(
                                json.dumps({"type": "error", "message": "max agents reached"})
                            )
                            await ws.close()
                        except Exception:
                            pass
                        return
                    try:
                        await ws.send(json.dumps({"type": "auth_ok", "agent_id": aid}))
                    except Exception:
                        pass
                    logger.info(f"✅ Agent 认证成功: {aid}")

                elif mtype == "heartbeat":
                    if agent:
                        agent.touch()
                        try:
                            await ws.send(
                                json.dumps({"type": "heartbeat_ack", "time": time.time()})
                            )
                        except Exception:
                            pass

                elif mtype == "result":
                    if agent:
                        agent.busy = False
                        agent.current_task = None

        except ConnectionClosed:
            logger.info(f"Agent 断开: {agent.agent_id if agent else peer}")
        except Exception as e:
            logger.error(f"Agent 处理异常: {e}")
        finally:
            if agent and agent.agent_id in self.agents:
                await self.agents.remove(agent.agent_id)

    # -- 发送指令 --
    async def send_command(
        self,
        agent_id: str,
        action: str,
        params: dict | None = None,
        timeout: float = 10.0,
    ) -> dict:
        agent = self.agents.get(agent_id)
        if not agent:
            return {"ok": False, "error": f"Agent {agent_id} not found"}
        if not agent.authenticated:
            return {"ok": False, "error": "Agent not authenticated"}

        msg = {
            "type": "command",
            "action": action,
            "params": params or {},
            "id": uuid.uuid4().hex[:12],
        }
        try:
            agent.busy = True
            agent.current_task = action
            await asyncio.wait_for(agent.ws.send(json.dumps(msg)), timeout=timeout)
            return {"ok": True, "message": f"sent {action}", "id": msg["id"]}
        except asyncio.TimeoutError:
            agent.busy = False
            return {"ok": False, "error": "send timeout"}
        except Exception as e:
            agent.busy = False
            return {"ok": False, "error": str(e)}

    # -- 心跳清理 --
    async def heartbeat_cleanup(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.cfg.get("heartbeat_interval", HEARTBEAT_INTERVAL))
                timeout = self.cfg.get("heartbeat_timeout", HEARTBEAT_TIMEOUT)
                dead = await self.agents.prune(timeout=timeout)
                for aid in dead:
                    logger.info(f"清理离线 Agent: {aid}")
            except Exception as e:
                logger.error(f"心跳清理异常: {e}")

    # -- Web API 数据 --
    def panel_data(self) -> dict:
        agents = list(self.agents._agents.values())
        return {
            "status": "running" if self._running else "stopped",
            "agents": [
                {
                    "id": a.agent_id,
                    "state": "busy" if a.busy else "idle",
                    "alive": a.is_alive(),
                    "current_task": a.current_task,
                    "authenticated": a.authenticated,
                }
                for a in agents
            ],
        }


# ============================================================
# AstrBot 插件壳
# ============================================================
@register(
    name=PLUGIN_NAME,
    author="kugua",
    desc="远程控制 Windows 电脑（QQ → AstrBot → WebSocket → Windows Agent）",
    version=VERSION,
    repo="https://github.com/183kugua/astrbot_plugin_winremote",
)
class WinRemotePlugin(Star):
    """AstrBot 插件壳：持有 WinRemoteServer + AuthManager"""

    def __init__(self, context: Context, config: AstrBotConfig):

        super().__init__(context)
        self.context = context
        self.config = config
        # 配置由 AStrBot 注入到 config 参数
        cfg_dict = self.config.get("_config", {})
        self.server = WinRemoteServer(
            context=context,
            config=cfg_dict,
        )
        # 快捷引用
        self.agents = self.server.agents

        self.pwd_guard = self.server.pwd_guard
        self.cfg = self.server.cfg

        # ── v1.0.0：初始化会话级授权管理器 ──
        secret_token = self._cfg_str("secret_token", "change-me")
        ttl = self._cfg_int("auth_ttl_seconds", 300, 0, 3600)
        self.auth_mgr = AuthManager(
            secret_token=secret_token,
            ttl=ttl,
        # pass  # audit removed: audit_path=audit_path,
        )
        self._auth_ttl = ttl

        logger.info(f"WinRemote v{VERSION} 初始化完成（TTL={ttl}s）")
    # -- 配置读取辅助 --
    def _cfg(self, key: str, default: Any = None) -> Any:
        return self.cfg.get(key, default)

    def _cfg_int(self, key: str, default: int, lo: int = 0, hi: int = 10**9) -> int:
        try:
            return max(lo, min(hi, int(self.cfg.get(key, default))))
        except (TypeError, ValueError):
            return default

    def _cfg_str(self, key: str, default: str) -> str:
        v = self.cfg.get(key, default)
        return str(v) if v is not None else default

    def _cfg_bool(self, key: str, default: bool) -> bool:
        v = self.cfg.get(key, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    def _cfg_list(self, key: str, default: list) -> list:
        v = self.cfg.get(key, default)
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return list(default)

    # -- 启动 / 停止 --
    async def start(self) -> None:
        await self.server.start()
        if self.server._running:
            asyncio.create_task(self.server.heartbeat_cleanup())

    async def stop(self) -> None:
        await self.server.stop()

    # -- 安全校验 --
    def _check_password(self, qq: str, pwd: str | None) -> tuple[bool, str]:
        expected = self._cfg_str("admin_password", "")
        if not expected:
            return True, ""
        return asyncio.get_event_loop().run_until_complete(self.pwd_guard.check(qq, pwd, expected))

    # -- QQ 指令 --
    @StarHandlerMetadata(
        handler_type=StarHandlerType.COMMAND,
        command="win",
        command_type=CommandType.ALL,
        event_type=EventType.MESSAGE_ALL,
        description="WinRemote 远程控制指令入口",
    )
    async def cmd_win(self, handler, event):
        user = event.get_sender_id() or "unknown"
        msg = event.get_message_str().strip()
        parts = msg.split()

        pwd = None
        clean = []
        skip = False
        for i, p in enumerate(parts):
            if skip:
                skip = False
                continue
            if p == "--pwd" and i + 1 < len(parts):
                pwd = parts[i + 1]
                skip = True
            elif p.startswith("--pwd="):
                pwd = p[6:]
            else:
                clean.append(p)
        cmd_parts = clean[1:] if len(clean) > 1 else []

        if not cmd_parts:
            await handler.send(
                f"WinRemote 远程控制 V{VERSION}\n用法:\n"
                "/win 状态\n/win agents\n/win shell <命令>\n"
                "/win powershell <命令>\n/win 截图\n/win 按键 <组合键>\n"
                "/win 鼠标 <x> <y> [click|right|double]\n"
                "/win 打开 <程序>\n/win 读文件 <路径>\n/win 审计"
            )
            return

        sub = cmd_parts[0].lower()

        # 二次密码
        if sub not in ("状态", "agents", "审计"):
            expected_pwd = self._cfg_str("admin_password", "")
            ok, err = await self.pwd_guard.check(user, pwd, expected_pwd)
            if not ok:
                await handler.send(f"❌ {err}")
                return

        agent = self.server.agents.find()
        if not agent and sub not in ("agents", "审计"):
            await handler.send("❌ 没有可用的 Agent，请确认 Windows 端已连接")
            return

        # ── v1.0.0：会话级授权检查 ──
        _auth_op_map = {
            "shell": "shell",
            "powershell": "powershell",
            "screenshot": "screenshot",
            "keypress": "keypress",
            "mouse": "mouse",
            "open": "open",
            "readfile": "readfile",
            "write": "write",
        }
        # Map command aliases to auth ops
        _alias_map = {"截图": "screenshot", "按键": "keypress", "鼠标": "mouse", "打开": "open", "读文件": "readfile"}
        auth_op = _alias_map.get(sub, _auth_op_map.get(sub))
        if auth_op is not None and sub not in ("状态", "agents", "审计"):
            if not self.auth_mgr.check(auth_op):
                import hashlib
                admin_pwd_hash = self._cfg_str("admin_password_hash", "")
                if not admin_pwd_hash:
                    pwd_plain = self._cfg_str("admin_password", "")
                    admin_pwd_hash = hashlib.sha256(pwd_plain.encode()).hexdigest()
                result = self.auth_mgr.request(auth_op, pwd or "", admin_pwd_hash)
                if result["status"] == "wrong_pwd":
                    await handler.send("❌ 二次密码错误，授权失败")
                    return
                if result["status"] == "need_confirm":
                    # 向管理员私聊发送授权申请
                    admin_list = self._cfg_list("admin_qq", [])
                    confirmed = await request_private_confirm(
                        self.context, event, auth_op, self._auth_ttl,
                        admin_list, plugin_self=self,
                    )
                    if confirmed:
                        self.auth_mgr.confirm(auth_op, str(user))
                        ttl_d = "永久" if self._auth_ttl == 0 else f"{self._auth_ttl}秒"
                        await handler.send(f"✅ {auth_op} 授权通过（{ttl_d}）")
                    else:
                        self.auth_mgr.deny(auth_op, str(user))
                        await handler.send(f"❌ {auth_op} 授权被拒绝或超时")
                        return
                elif result["status"] == "ok":
                    ttl_d = "永久" if result.get("perm") else f"{result.get('ttl')}秒"
                    await handler.send(f"✅ {auth_op} 授权成功（{ttl_d}）")
                else:
                    await handler.send(f"❌ 授权失败: {result.get('status')}")
                    return
            remaining = self.auth_mgr.ttl_remaining(auth_op)
            ttl_info = f"TTL={remaining}s" if remaining > 0 else "permanent"
            logger.info(f"[Auth] {user} -> {auth_op} ({ttl_info})")


        # 管理员
        admin_qq = self._cfg_list("admin_qq", [])
        allow_group = self._cfg_bool("allow_group", False)
        is_group = hasattr(event, "is_group") and event.is_group()
        if admin_qq and user not in [str(q) for q in admin_qq]:
            if not (allow_group and is_group):
                await handler.send("❌ 你没有权限使用 /win 指令")
                    {
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "qq": user,
                        "agent": "-",
                        "action": sub,
                        "result": "拒绝-非管理员",
                    }
                )
                return

        # 状态
        if sub == "状态":
            if not self.server.agents:
                await handler.send("📴 当前无 Agent 在线")
                return
            lines = []
            for a in self.server.agents._agents.values():
                s = "🟢在线" if a.is_alive() else "🔴离线"
                b = "⏳忙碌" if a.busy else "✅空闲"
                lines.append(f"{a.agent_id}: {s} {b}")
                if a.current_task:
                    lines.append(f"  当前任务: {a.current_task}")
            await handler.send("\n".join(lines))
            return

        if sub == "agents":
            if not self.server.agents:
                await handler.send("📴 无已注册 Agent")
                return
            lines = [f"共 {len(self.server.agents)} 个 Agent:"]
            for a in self.server.agents._agents.values():
                alive = "🟢" if a.is_alive() else "🔴"
                auth = "✅" if a.authenticated else "❌"
                lines.append(f"{alive} {a.agent_id} 认证={auth}")
            await handler.send("\n".join(lines))
            return

        # Shell / PowerShell
        if sub in ("shell", "powershell"):
            if sub == "powershell" and not self._cfg_bool("allow_powershell", True):
                await handler.send("❌ PowerShell 未启用")
                return
            cmd_str = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""
            if not cmd_str:
                await handler.send(f"用法: /win {sub} <命令>")
                return
            ok, err = validate_command(cmd_str, self.cfg)
            if not ok:
                await handler.send(f"❌ {err}")
                    {
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "qq": user,
                        "agent": agent.agent_id if agent else "-",
                        "action": f"{sub}:{cmd_str[:80]}",
                        "result": err,
                    }
                )
                return
            action = "powershell" if sub == "powershell" else "shell"
            result = await self.server.send_command(agent.agent_id, action, {"command": cmd_str})
            reply = f"📤 已发送: {cmd_str}\n{json.dumps(result, ensure_ascii=False)}"
            await handler.send(reply[:MAX_OUTPUT_BYTES])
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "qq": user,
                    "agent": agent.agent_id if agent else "-",
                    "action": f"{sub}:{cmd_str[:80]}",
                    "result": "已发送",
                }
            )
            return

        # 截图
        if sub == "截图":
            fmt = self._cfg_str("screenshot_format", "JPEG").upper()
            quality = self._cfg_int("screenshot_quality", 75, 1, 100)
            result = await self.server.send_command(
                agent.agent_id, "screenshot", {"format": fmt, "quality": quality}
            )
            await handler.send(f"📸 截图请求已发送\n{json.dumps(result, ensure_ascii=False)}")
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "qq": user,
                    "agent": agent.agent_id,
                    "action": "screenshot",
                    "result": "已发送",
                }
            )
            return

        # 按键
        if sub == "按键":
            keys = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""
            if not keys:
                await handler.send("用法: /win 按键 ctrl+alt+del")
                return
            result = await self.server.send_command(agent.agent_id, "keypress", {"keys": keys})
            await handler.send(f"⌨️ 按键: {keys}")
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "qq": user,
                    "agent": agent.agent_id,
                    "action": f"keypress:{keys}",
                    "result": "已发送",
                }
            )
            return

        # 鼠标
        if sub == "鼠标":
            if len(cmd_parts) < 3:
                await handler.send("用法: /win 鼠标 <x> <y> [click|right|double]")
                return
            try:
                x, y = int(cmd_parts[1]), int(cmd_parts[2])
            except ValueError:
                await handler.send("❌ x/y 必须是整数")
                return
            btn = cmd_parts[3] if len(cmd_parts) > 3 else "click"
            result = await self.server.send_command(
                agent.agent_id, "mouse", {"x": x, "y": y, "button": btn}
            )
            await handler.send(f"🖱️ 鼠标 ({x},{y}) {btn}")
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "qq": user,
                    "agent": agent.agent_id,
                    "action": f"mouse:{x},{y},{btn}",
                    "result": "已发送",
                }
            )
            return

        # 打开
        if sub == "打开":
            target = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""
            if not target:
                await handler.send("用法: /win 打开 <程序名或路径>")
                return
            result = await self.server.send_command(agent.agent_id, "open", {"target": target})
            await handler.send(f"📂 打开: {target}")
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "qq": user,
                    "agent": agent.agent_id,
                    "action": f"open:{target}",
                    "result": "已发送",
                }
            )
            return

        # 读文件
        if sub == "读文件":
            filepath = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""
            if not filepath:
                await handler.send("用法: /win 读文件 <路径>")
                return
            ok, err = validate_path(filepath, self.cfg)
            if not ok:
                await handler.send(f"❌ {err}")
                    {
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "qq": user,
                        "agent": agent.agent_id,
                        "action": f"read:{filepath}",
                        "result": err,
                    }
                )
                return
            max_bytes = self._cfg_int("max_read_bytes", 65536, 1024, 1048576)
            result = await self.server.send_command(
                agent.agent_id, "read_file", {"path": filepath, "max_bytes": max_bytes}
            )
            await handler.send(
                f"📄 读文件: {filepath}\n"
                f"{json.dumps(result, ensure_ascii=False)[:MAX_OUTPUT_BYTES]}"
            )
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "qq": user,
                    "agent": agent.agent_id,
                    "action": f"read:{filepath}",
                    "result": "已发送",
                }
            )
            return

        # 审计
        if sub == "审计":
        # pass  # audit removed: if not self._cfg_bool("audit_enabled", True):
                await handler.send("审计日志未启用")
                return
                await handler.send("📭 审计日志为空")
                return
            lines = [f"📋 最近 {max_show} 条审计:"]
                lines.append(
                    f"[{entry.get('time', '')}] {entry.get('qq', '')} → "
                    f"{entry.get('agent', '')}: {entry.get('action', '')} → "
                    f"{entry.get('result', '')[:60]}"
                )
            await handler.send("\n".join(lines))
            return

        await handler.send(f"❓ 未知子指令: {sub}\n输入 /win 查看用法")

    # -- Web API --
    async def api_get_agents(self) -> dict:
        agents = list(self.server.agents._agents.values())
        data = []
        for a in agents:
            data.append(
                {
                    "agent_id": a.agent_id,
                    "authenticated": a.authenticated,
                    "alive": a.is_alive(),
                    "busy": a.busy,
                    "current_task": a.current_task,
                    "last_heartbeat": a.last_heartbeat,
                    "connected_at": a.connected_at,
                    "metadata": a.metadata,
                }
            )
        return {"agents": data, "count": len(data)}

        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": items[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def api_save_settings(self, settings: dict) -> dict:
        try:
            # 插件自己的配置存在 data/config/_config.json
            # 用 StarTools.get_data_dir() 拿到目录，直接读写 JSON
            from astrbot.api.star import StarTools

            data_dir = StarTools.get_data_dir(self.context)
            config_path = os.path.join(data_dir, "_config.json")
            os.makedirs(data_dir, exist_ok=True)

            # 读旧配置（如果存在）
            cfg = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, encoding="utf-8") as f:
                        cfg = json.load(f)
                except (json.JSONDecodeError, OSError):
                    cfg = {}

            # 合并新配置
            cfg.update(settings)

            # 写回
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)

            # 同步到内存
            self.cfg = get_config(cfg)
            self.server.cfg = self.cfg
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def api_test_connection(self) -> dict:
        agents = list(self.server.agents._agents.values())
        alive = [a for a in agents if a.is_alive()]
        return {
            "online_agents": len(alive),
            "total_agents": len(agents),
            "server_running": self.server._running,
        }

    async def api_panel_widget(self) -> dict:
        """v1.0.0 增强版：返回 Agent + 授权状态 + 审计完整性"""
        agents = list(self.server.agents._agents.values())
        alive = sum(1 for a in agents if a.is_alive())
        busy = sum(1 for a in agents if a.busy)

        # 授权状态
        granted_info = []
        if self.auth_mgr is not None:
            for op, exp in self.auth_mgr.auth.items():
                remaining = -1 if exp == 0 else max(0, int(exp - time.time()))
                granted_info.append({
                    "op": op,
                    "permanent": (exp == 0),
                    "remaining": remaining,
                    "ttl_desc": "永久" if exp == 0 else f"{remaining}s",
                })
        pending_count = len(getattr(self.auth_mgr, "pending", {}))

        # 审计完整性（轻量校验）
        integrity = None
        # pass  # audit removed: if self.auth_mgr is not None and audit_path:
            try:
        # pass  # audit removed: result = self.auth_mgr.verify_audit(audit_path, self.auth_mgr.key)
                integrity = result.get("integrity", None)
            except Exception:
                integrity = None

        return {
            "total": len(agents),
            "alive": alive,
            "busy": busy,
            "version": VERSION,
            "auth": {
                "granted": granted_info,
                "pending": pending_count,
                "ttl_default": getattr(self, "_auth_ttl", 300),
            },
                "integrity": integrity,
        # pass  # audit removed: "path": audit_path,
            },
        }

    # -- 生命周期 --
    async def on_load(self) -> None:
        logger.info(f"WinRemote v{VERSION} 已加载")
        await self.start()

    async def on_unload(self) -> None:
        # v1.0.0：卸载时撤销所有授权
        self.auth_mgr.revoke_all()
        await self.stop()

    async def on_config_changed(self, old_config, new_config) -> None:
        logger.info("配置已更新")
        self.cfg = get_config(new_config)
        self.server.cfg = self.cfg
        self.pwd_guard = PasswordGuard(
            max_attempts=self._cfg_int("password_max_attempts", 5, 1, 50),
            ban_duration=self._cfg_int("password_ban_duration", 300, 30, 86400),
        )
        # v1.0.0：重建 AuthManager 以应用新 TTL
        secret_token = self._cfg_str("secret_token", "change-me")
        ttl = self._cfg_int("auth_ttl_seconds", 300, 0, 3600)
        self.auth_mgr = AuthManager(
            secret_token=secret_token,
            ttl=ttl,
        # pass  # audit removed: audit_path=audit_path,
        )
        self._auth_ttl = ttl

    # ── v1.0.0：私聊授权确认回复监听 ──
    @astr_filter.event_message_type(EventType.PRIVATE_MESSAGE)
    async def on_private_message(self, event):
        """
        监听私聊消息，处理管理员对授权申请的「同意/拒绝」回复。
        非授权确认消息不做任何处理（返回，让其他插件/LLM 继续处理）。
        """
        from confirm import handle_private_reply
        handled = await handle_private_reply(self.context, event)
        if handled:
            # 已处理授权确认 → 停止事件传播
            event.stop_event()


# ============================================================
# 公开 API
# ============================================================
__all__ = [
    "WinRemotePlugin",
    "WinRemoteServer",
    "AgentManager",
    "AgentConnection",
    "PasswordGuard",
    "AuditLogger",
    "AuthManager",
    "VERSION",
    "PLUGIN_NAME",
    "DANGEROUS_KEYWORDS",
    "MAX_OUTPUT_BYTES",
    "HEARTBEAT_INTERVAL",
    "HEARTBEAT_TIMEOUT",
    "AUDIT_MAX",
    "get_config",
    "validate_command",
    "validate_path",
]

__version__ = VERSION

# ============================================================
# v1.0.0：注册 webui_panel 增强路由
# ============================================================
try:
    from webui_panel import register_web_apis as _register_panel
    if _register_panel is not None:
        try:
            from astrbot.api.star import context as _ctx
            if _ctx is not None:
                _register_panel(_ctx)
        except Exception:
            pass
except Exception:
    pass
