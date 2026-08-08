"""
astrbot_plugin_winremote.py — AStrBot V1.0.2 (fixed)
=====================================================
修复:
- ws_host 默认 0.0.0.0
- 在 __init__ 中直接调度 start()，不依赖 AstrBot 生命周期
"""

from __future__ import annotations

import asyncio
import base64
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

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from auth import AuthManager

SCHEMA_TYPE_WHITELIST = frozenset({
    "int", "float", "bool", "string", "text",
    "list", "file", "object", "template_list", "dict",
})

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
    _HAS_WS = True
except ImportError:
    websockets = None
    ConnectionClosed = Exception
    _HAS_WS = False

try:
    from astrbot.api import AstrBotConfig
    from astrbot.api import logger as ab_logger
    from astrbot.api.event import filter as astr_filter
    from astrbot.api.star import Context, Star, register
    from astrbot.core.star.register.star_handler import register_command
    _HAS_ASTRBOT = True
    class _EnumFallback:
        def __getattr__(self, name): return name
    CommandType = _EnumFallback()
    StarHandlerType = _EnumFallback()
except ImportError:
    AstrBotConfig = dict
    ab_logger = None
    Context = Any
    Star = object
    def register_command(*a, **kw):
        def deco(func): return func
        return deco
    def register(*a, **kw):
        def deco(cls): return cls
        return deco
    class _FilterFallback:
        def __call__(self, *a, **kw):
            def deco(func): return func
            return deco
        def __getattr__(self, name): return self
    astr_filter = _FilterFallback()
    StarTools = None
    class _EnumFallback:
        def __getattr__(self, name): return name
    StarHandlerType = _EnumFallback()
    EventType = _EnumFallback()
    CommandType = _EnumFallback()
    _HAS_ASTRBOT = False

PLUGIN_NAME = "astrbot_plugin_winremote"
VERSION = "1.0.2"
__version__ = VERSION

DANGEROUS_KEYWORDS = [
    "rm ", "del ", "format", "shutdown", "reboot", "mkfs",
    "dd if=", "reg add", "reg delete", "net user",
    ":(){ :|:& };:", "wget ", "curl ",
]
INJECTION_CHARS = ["&&", "||", ";", "`", "$(", "| ", " >", " <", ">>", "<<"]

MAX_OUTPUT_BYTES = 8192
STREAM_CHUNK_SIZE = 1024
STREAM_INTERVAL = 0.5
HEARTBEAT_INTERVAL = 15
HEARTBEAT_TIMEOUT = 45
AUDIT_MAX = 1000

logger = logging.getLogger(f"AstrBot.{PLUGIN_NAME}")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(f"[%(asctime)s] [{PLUGIN_NAME}] [%(levelname)s] %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


class AgentConnection:
    def __init__(self, ws=None, agent_id: str = "unknown"):
        self.agent_id = agent_id
        self.ws = ws
        self.metadata: dict = {}
        self.authenticated: bool = False
        self.last_heartbeat = time.time()
        self.current_task: str | None = None
        self.connected_at = time.time()
        self.busy: bool = False
        self.pending_requests: dict[str, asyncio.Future] = {}

    def is_alive(self, timeout: int = HEARTBEAT_TIMEOUT) -> bool:
        return (time.time() - self.last_heartbeat) < timeout

    def touch(self) -> None:
        self.last_heartbeat = time.time()

    def __repr__(self) -> str:
        s = "认证" if self.authenticated else "未认证"
        a = "在线" if self.is_alive() else "离线"
        return f"Agent({self.agent_id}, {a}, {s})"


class AgentManager:
    def __init__(self, max_agents: int = 8):
        self._agents: dict[str, AgentConnection] = {}
        self.max_agents = max_agents

    def __len__(self) -> int: return len(self._agents)
    def __contains__(self, agent_id: str) -> bool: return agent_id in self._agents

    async def add(self, agent: AgentConnection) -> bool:
        if len(self._agents) >= self.max_agents: return False
        self._agents[agent.agent_id] = agent
        return True

    async def remove(self, agent_id: str) -> None:
        if agent_id in self._agents:
            try: await self._agents[agent_id].ws.close()
            except Exception: pass
            del self._agents[agent_id]

    async def list(self) -> list[AgentConnection]:
        return list(self._agents.values())

    def get(self, agent_id: str) -> AgentConnection | None:
        return self._agents.get(agent_id)

    def find(self, name: str | None = None) -> AgentConnection | None:
        if not self._agents: return None
        if name:
            for a in self._agents.values():
                if a.agent_id == name or a.agent_id.startswith(name):
                    return a
            return None
        for a in self._agents.values():
            if a.is_alive(): return a
        return None

    async def prune(self, timeout: int = HEARTBEAT_TIMEOUT) -> list[str]:
        dead = [aid for aid, a in self._agents.items() if not a.is_alive(timeout)]
        for aid in dead:
            try: await self._agents[aid].ws.close()
            except Exception: pass
            del self._agents[aid]
        return dead


class PasswordGuard:
    def __init__(self, max_attempts: int = 5, ban_duration: int = 300):
        self.max_attempts = max_attempts
        self.ban_duration = ban_duration
        self._attempts: dict[str, list[float]] = {}

    async def check(self, peer: str, provided: str | None, expected: str) -> tuple[bool, str]:
        if await self.is_banned(peer):
            return False, f"密码错误次数过多，封禁 {self.ban_duration} 秒"
        if not expected: return True, ""
        if not provided: return False, "需要二次密码"
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
        if not fails: return False
        now = time.time()
        fails = [t for t in fails if now - t < self.ban_duration]
        self._attempts[peer] = fails
        return len(fails) >= self.max_attempts


def get_config(user_config: Any = None) -> dict:
    defaults: dict = {
        "ws_host": "0.0.0.0",
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
        "command_whitelist": ["shell", "powershell", "screenshot", "keypress", "mouse", "open", "readfile"],
        "command_blacklist": list(DANGEROUS_KEYWORDS),
        "command_regex_blacklist": [r"powershell\s+-enc", r"cmd\s+/c\s+\"", r"&&", r"\|\|", r";\s*rm", r";\s*del", r"\$$.*$"],
        "allow_powershell": True,
        "strict_whitelist": False,
        "path_whitelist": ["C:\\Temp", "C:\\Users\\Public", "D:\\Shared"],
        "path_blacklist_keywords": ["..\\", "../", "%USERPROFILE%", "%SYSTEMROOT%", "C:\\Windows", "C:\\Program Files"],
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
    if user_config is None: return dict(defaults)
    merged = dict(defaults)
    if isinstance(user_config, dict):
        for k, v in user_config.items():
            if k in defaults: merged[k] = v
        return merged
    try:
        for k in defaults:
            val = user_config.get(k, None)
            if val is not None: merged[k] = val
    except Exception: pass
    return merged


def validate_command(cmd: str, config: dict | None = None) -> tuple[bool, str]:
    if config is None: config = get_config()
    cmd_s = (cmd or "").strip()
    if not cmd_s: return False, "empty command"
    blacklist = config.get("command_blacklist", DANGEROUS_KEYWORDS)
    cmd_lower = cmd_s.lower()
    for kw in blacklist:
        if kw.lower() in cmd_lower: return False, f"blacklist hit: {kw}"
    for ch in INJECTION_CHARS:
        if ch in cmd_s: return False, f"injection char: {ch}"
    regex_black = config.get("command_regex_blacklist", [])
    for pattern in regex_black:
        try:
            if re.search(pattern, cmd_s): return False, f"regex blacklist: {pattern}"
        except re.error: continue
    strict = config.get("strict_whitelist", False)
    whitelist = config.get("command_whitelist", [])
    if strict and whitelist:
        first = cmd_s.split()[0] if cmd_s.split() else ""
        if not any(first.lower().startswith(w.lower()) for w in whitelist):
            return False, f"not in whitelist: {first}"
    return True, ""


def validate_path(filepath: str, config: dict | None = None) -> tuple[bool, str]:
    if config is None: config = get_config()
    if not filepath or not str(filepath).strip(): return False, "empty path"
    whitelist = config.get("path_whitelist", [])
    blacklist_kw = config.get("path_blacklist_keywords", [])
    fp = str(filepath)
    fp_lower = fp.lower()
    for kw in blacklist_kw:
        if kw.lower() in fp_lower: return False, f"forbidden keyword: {kw}"
    if whitelist:
        allowed = any(fp_lower.startswith(str(w).lower()) for w in whitelist)
        if not allowed: return False, f"not in whitelist: {filepath}"
    return True, ""


class WinRemoteServer:
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

    async def start(self) -> None:
        if self._running:
            logger.info("WebSocket 已在运行，跳过")
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
            logger.info(f"=== 监听中 ws://{host}:{port} ===")
        except Exception as e:
            logger.error(f"启动失败: {e}")
            self._running = False

    async def stop(self) -> None:
        self._running = False
        for a in list(self.agents._agents.values()):
            try: await a.ws.close()
            except Exception: pass
        self.agents._agents.clear()
        if self._ws_server:
            self._ws_server.close()
            try: await self._ws_server.wait_closed()
            except Exception: pass
            self._ws_server = None

    async def _handle_agent(self, ws, require_encryption: bool = False) -> None:
        peer = getattr(ws, "remote_address", ("?", "?"))[0]
        logger.info(f"Agent 连接来自 {peer}")
        if require_encryption and not getattr(ws, "secure", False):
            logger.warning(f"拒绝非加密连接 {peer}")
            try:
                await ws.send(json.dumps({"type": "error", "message": "Encryption required. Use wss://"}))
                await ws.close()
            except Exception: pass
            return
        expected = self.cfg["secret_token"]
        if not expected:
            try:
                await ws.send(json.dumps({"type": "error", "message": "server misconfigured: secret_token empty"}))
                await ws.close()
            except Exception: pass
            return
        agent: AgentConnection | None = None
        try:
            async for raw in ws:
                try: msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug(f"忽略非 JSON: {str(raw)[:80]}")
                    continue
                mtype = msg.get("type", "")
                if mtype == "handshake":
                    token = msg.get("token", "")
                    if token != expected:
                        logger.warning(f"认证失败 from {peer}")
                        try: await ws.send(json.dumps({"type": "error", "message": "Invalid token"}))
                        except Exception: pass
                        break
                    aid = msg.get("agent_id", f"agent-{uuid.uuid4().hex[:8]}")
                    agent = AgentConnection(ws=ws, agent_id=aid)
                    agent.authenticated = True
                    agent.touch()
                    ok = await self.agents.add(agent)
                    if not ok:
                        logger.warning(f"Agent 数达上限，拒绝 {aid}")
                        try:
                            await ws.send(json.dumps({"type": "error", "message": "max agents reached"}))
                            await ws.close()
                        except Exception: pass
                        return
                    try: await ws.send(json.dumps({"type": "auth_ok", "agent_id": aid}))
                    except Exception: pass
                    logger.info(f"Agent 认证成功: {aid}")
                elif mtype == "heartbeat":
                    if agent:
                        agent.touch()
                        try: await ws.send(json.dumps({"type": "heartbeat_ack", "time": time.time()}))
                        except Exception: pass
                elif mtype == "result":
                    if agent:
                        agent.busy = False
                        agent.current_task = None
                        rid = msg.get("id", "")
                        if rid and rid in agent.pending_requests:
                            fut = agent.pending_requests[rid]
                            if not fut.done():
                                fut.set_result({"result": msg.get("result", {}), "format": None, "data": None})
                            else:
                                prev = fut.result()
                                prev["result"] = msg.get("result", {})
                elif mtype == "chunk":
                    if agent:
                        rid = msg.get("id", "")
                        if rid and rid in agent.pending_requests:
                            fut = agent.pending_requests[rid]
                            if not fut.done():
                                fut.set_result({"result": {}, "format": msg.get("format", "image/jpeg"), "data": msg.get("data", "")})
                            else:
                                prev = fut.result()
                                prev["data"] = msg.get("data", "")
                                prev["format"] = msg.get("format", "image/jpeg")
        except ConnectionClosed:
            logger.info(f"Agent 断开: {agent.agent_id if agent else peer}")
        except Exception as e:
            logger.error(f"Agent 处理异常: {e}")
        finally:
            if agent and agent.agent_id in self.agents:
                await self.agents.remove(agent.agent_id)

    async def send_command(self, agent_id: str, action: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        agent = self.agents.get(agent_id)
        if not agent: return {"ok": False, "error": f"Agent {agent_id} not found"}
        if not agent.authenticated: return {"ok": False, "error": "Agent not authenticated"}
        msg_id = uuid.uuid4().hex[:12]
        msg = {"type": "command", "action": action, "params": params or {}, "id": msg_id}
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        agent.pending_requests[msg_id] = future
        try:
            agent.busy = True
            agent.current_task = action
            await asyncio.wait_for(agent.ws.send(json.dumps(msg)), timeout=10.0)
            result = await asyncio.wait_for(future, timeout=timeout)
            agent_result = result.get("result", {})
            merged = {"ok": True, "id": msg_id}
            if isinstance(agent_result, dict):
                merged.update(agent_result)
            if action == "screenshot" and "data" in result:
                merged["data"] = result["data"]
                merged["format"] = result.get("format", "image/jpeg")
            return merged
        except asyncio.TimeoutError:
            return {"ok": False, "error": f"Agent 响应超时 ({timeout}s)", "id": msg_id}
        except Exception as e:
            return {"ok": False, "error": str(e), "id": msg_id}
        finally:
            agent.busy = False
            agent.current_task = None
            agent.pending_requests.pop(msg_id, None)

    async def heartbeat_cleanup(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.cfg.get("heartbeat_interval", HEARTBEAT_INTERVAL))
                timeout = self.cfg.get("heartbeat_timeout", HEARTBEAT_TIMEOUT)
                dead = await self.agents.prune(timeout=timeout)
                for aid in dead: logger.info(f"清理离线 Agent: {aid}")
            except Exception as e:
                logger.error(f"心跳清理异常: {e}")

    def panel_data(self) -> dict:
        agents = list(self.agents._agents.values())
        return {
            "status": "running" if self._running else "stopped",
            "agents": [{"id": a.agent_id, "state": "busy" if a.busy else "idle", "alive": a.is_alive(), "current_task": a.current_task, "authenticated": a.authenticated} for a in agents],
        }


@register(name=PLUGIN_NAME, author="kugua", desc="远程控制 Windows 电脑（QQ -> AstrBot -> WebSocket -> Windows Agent）", version=VERSION, repo="https://github.com/183kugua/astrbot_plugin_winremote")
class WinRemotePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        cfg_dict = self.config.get("_config", {})
        logger.info(f"[WinRemote] 配置加载: ws_host={cfg_dict.get('ws_host', '(默认)')}")
        self.server = WinRemoteServer(context=context, config=cfg_dict)
        self.agents = self.server.agents
        self.pwd_guard = self.server.pwd_guard
        self.cfg = self.server.cfg
        logger.info(f"[WinRemote] 最终配置: ws_host={self.cfg['ws_host']}, ws_port={self.cfg['ws_port']}")
        secret_token = self._cfg_str("secret_token", "change-me")
        ttl = self._cfg_int("auth_ttl_seconds", 300, 0, 3600)
        self.auth_mgr = AuthManager(secret_token=secret_token, ttl=ttl)
        self._auth_ttl = ttl
        logger.info(f"WinRemote v{VERSION} 初始化完成（TTL={ttl}s）")
        # 直接在 __init__ 中调度启动，不依赖 AstrBot 调用 start()
        logger.info("[WinRemote] 在 __init__ 中调度 start()...")
        asyncio.ensure_future(self._delayed_start())

    async def _delayed_start(self):
        """延迟 1 秒启动，确保 AstrBot 事件循环就绪"""
        await asyncio.sleep(1)
        await self.start()

    async def start(self) -> None:
        logger.info("[WinRemote] start() 被调用！正在启动 WebSocket...")
        await self.server.start()
        if self.server._running:
            logger.info("[WinRemote] WebSocket 启动成功！")
            asyncio.create_task(self.server.heartbeat_cleanup())
        else:
            logger.error("[WinRemote] WebSocket 启动失败！")

    async def stop(self) -> None:
        await self.server.stop()

    def _cfg(self, key: str, default: Any = None) -> Any: return self.cfg.get(key, default)
    def _cfg_int(self, key: str, default: int, lo: int = 0, hi: int = 10**9) -> int:
        try: return max(lo, min(hi, int(self.cfg.get(key, default))))
        except (TypeError, ValueError): return default
    def _cfg_str(self, key: str, default: str) -> str:
        v = self.cfg.get(key, default)
        return str(v) if v is not None else default
    def _cfg_bool(self, key: str, default: bool) -> bool:
        v = self.cfg.get(key, default)
        if isinstance(v, bool): return v
        if isinstance(v, str): return v.lower() in ("true", "1", "yes", "on")
        return bool(v)
    def _cfg_list(self, key: str, default: list) -> list:
        v = self.cfg.get(key, default)
        if isinstance(v, list): return v
        if isinstance(v, str): return [s.strip() for s in v.split(",") if s.strip()]
        return list(default)

    def _check_password(self, qq: str, pwd: str | None) -> tuple[bool, str]:
        expected = self._cfg_str("admin_password", "")
        if not expected: return True, ""
        return asyncio.get_event_loop().run_until_complete(self.pwd_guard.check(qq, pwd, expected))

    @register_command(command_name="win", desc="WinRemote 远程控制指令入口")
    async def cmd_win(self, handler, event):
        user = event.get_sender_id() or "unknown"
        msg = event.get_message_str().strip()
        parts = msg.split()
        pwd = None
        clean = []
        skip = False
        for i, p in enumerate(parts):
            if skip: skip = False; continue
            if p == "--pwd" and i + 1 < len(parts):
                pwd = parts[i + 1]; skip = True
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
        if sub not in ("状态", "agents", "审计"):
            expected_pwd = self._cfg_str("admin_password", "")
            ok, err = await self.pwd_guard.check(user, pwd, expected_pwd)
            if not ok:
                await handler.send(f"\u274c {err}")
                return
        agent = self.server.agents.find()
        if not agent and sub not in ("agents", "审计"):
            await handler.send("\u274c 没有可用的 Agent，请确认 Windows 端已连接")
            return
        _auth_op_map = {"shell": "shell", "powershell": "powershell", "screenshot": "screenshot", "keypress": "keypress", "mouse": "mouse", "open": "open", "readfile": "readfile", "write": "write"}
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
                    await handler.send("\u274c 二次密码错误，授权失败"); return
                if result["status"] == "need_confirm":
                    self.auth_mgr.confirm(auth_op, str(user))
                    ttl_d = "永久" if self._auth_ttl == 0 else f"{self._auth_ttl}秒"
                    await handler.send(f"\u2705 {auth_op} 授权通过（{ttl_d}）")
                elif result["status"] == "ok":
                    ttl_d = "永久" if result.get("perm") else f"{result.get('ttl')}秒"
                    await handler.send(f"\u2705 {auth_op} 授权成功（{ttl_d}）")
                else:
                    await handler.send(f"\u274c 授权失败: {result.get('status')}"); return
            remaining = self.auth_mgr.ttl_remaining(auth_op)
            logger.info(f"[Auth] {user} -> {auth_op} (TTL={remaining}s)")
        admin_qq = self._cfg_list("admin_qq", [])
        allow_group = self._cfg_bool("allow_group", False)
        is_group = hasattr(event, "is_group") and event.is_group()
        if admin_qq and user not in [str(q) for q in admin_qq]:
            if not (allow_group and is_group):
                await handler.send("\u274c 你没有权限使用 /win 指令"); return
        if sub == "状态":
            if not self.server.agents:
                await handler.send("\U0001f4f4 当前无 Agent 在线"); return
            lines = []
            for a in self.server.agents._agents.values():
                s = "\U0001f7e2在线" if a.is_alive() else "\U0001f534离线"
                b = "\u23f3忙碌" if a.busy else "\u2705空闲"
                lines.append(f"{a.agent_id}: {s} {b}")
                if a.current_task: lines.append(f"  当前任务: {a.current_task}")
            await handler.send("\n".join(lines)); return
        if sub == "agents":
            if not self.server.agents:
                await handler.send("\U0001f4f4 无已注册 Agent"); return
            lines = [f"共 {len(self.server.agents)} 个 Agent:"]
            for a in self.server.agents._agents.values():
                alive = "\U0001f7e2" if a.is_alive() else "\U0001f534"
                auth = "\u2705" if a.authenticated else "\u274c"
                lines.append(f"{alive} {a.agent_id} 认证={auth}")
            await handler.send("\n".join(lines)); return
        if sub in ("shell", "powershell"):
            if sub == "powershell" and not self._cfg_bool("allow_powershell", True):
                await handler.send("\u274c PowerShell 未启用"); return
            cmd_str = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""
            if not cmd_str:
                await handler.send(f"用法: /win {sub} <命令>"); return
            ok, err = validate_command(cmd_str, self.cfg)
            if not ok:
                await handler.send(f"\u274c {err}"); return
            await handler.send(f"\u23f3 正在执行 {sub} 命令...")
            result = await self.server.send_command(agent.agent_id, sub, {"command": cmd_str})
            if result.get("ok"):
                stdout = result.get("stdout", "")
                stderr = result.get("stderr", "")
                rc = result.get("returncode", 0)
                out = stdout[:4000] or "(无输出)"
                if stderr: out += f"\n[stderr] {stderr[:1000]}"
                await handler.send(f"\u2705 {sub} 完成 (exit={rc}):\n{out}")
            else:
                await handler.send(f"\u274c {sub} 失败: {result.get('error', '未知错误')}")
            return
        if sub == "截图":
            await handler.send("\U0001f4f8 正在截图...")
            fmt = self._cfg_str("screenshot_format", "JPEG")
            q = self._cfg_int("screenshot_quality", 75, 1, 100)
            result = await self.server.send_command(agent.agent_id, "screenshot", {"format": fmt, "quality": q})
            if result.get("ok") and result.get("data"):
                b64_data = result["data"]
                img_bytes = base64.b64decode(b64_data)
                mime = result.get("format", "image/jpeg")
                await handler.send(f"\U0001f4f8 截图成功 ({len(img_bytes)} bytes, {mime})")
            elif result.get("ok"):
                await handler.send("\U0001f4f8 截图请求已发送（Agent 未返回图片数据）")
            else:
                await handler.send(f"\u274c 截图失败: {result.get('error', '未知错误')}")
            return
        if sub == "按键":
            keys_str = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""
            if not keys_str:
                await handler.send("用法: /win 按键 <组合键>  如 /win 按键 ctrl+c"); return
            result = await self.server.send_command(agent.agent_id, "keypress", {"keys": keys_str})
            if result.get("ok"):
                await handler.send(f"\u2328\ufe0f 按键已发送: {keys_str}")
            else:
                await handler.send(f"\u274c 按键失败: {result.get('error', '未知错误')}")
            return
        if sub == "鼠标":
            mouse_args = cmd_parts[1:]
            if len(mouse_args) < 2:
                await handler.send("用法: /win 鼠标 <x> <y> [click|right|double]"); return
            try:
                mx, my = int(mouse_args[0]), int(mouse_args[1])
            except ValueError:
                await handler.send("\u274c x/y 必须是整数坐标"); return
            btn = mouse_args[2] if len(mouse_args) > 2 else "click"
            if btn not in ("click", "right", "double", "move"): btn = "click"
            result = await self.server.send_command(agent.agent_id, "mouse", {"x": mx, "y": my, "button": btn})
            if result.get("ok"):
                await handler.send(f"\U0001f5b1\ufe0f 鼠标操作成功: ({mx},{my}) {btn}")
            else:
                await handler.send(f"\u274c 鼠标操作失败: {result.get('error', '未知错误')}")
            return
        if sub == "打开":
            target = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""
            if not target:
                await handler.send("用法: /win 打开 <程序>  如 /win 打开 calc"); return
            result = await self.server.send_command(agent.agent_id, "open", {"target": target})
            if result.get("ok"):
                await handler.send(f"\U0001f4c2 已打开: {target}")
            else:
                await handler.send(f"\u274c 打开失败: {result.get('error', '未知错误')}")
            return
        if sub == "读文件":
            fpath = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""
            if not fpath:
                await handler.send("用法: /win 读文件 <路径>"); return
            ok, err = validate_path(fpath, self.cfg)
            if not ok:
                await handler.send(f"\u274c {err}"); return
            result = await self.server.send_command(agent.agent_id, "readfile", {"path": fpath, "max_bytes": self._cfg_int("max_read_bytes", 65536)})
            if result.get("ok"):
                content = result.get("content", "")
                await handler.send(f"\U0001f4c4 文件内容（{fpath}）:\n{content[:4000]}")
            else:
                await handler.send(f"\u274c 读取失败: {result.get('error', '未知错误')}")
            return
        if sub == "审计":
            await handler.send("\U0001f4cb 审计日志功能开发中")
            return
        await handler.send(f"\u274c 未知子命令: {sub}\n支持: 状态 agents shell powershell 截图 按键 鼠标 打开 读文件 审计")
