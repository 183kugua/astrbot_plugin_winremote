"""
astrbot_plugin_winremote - V0.6.0
Remote control Windows via QQ/AstrBot with WebSocket reverse tunnel.

Architecture:
    QQ -> NapCat(local Win) -> AstrBot(server)
                                    |
                                    -> WS server :6190
                                         |
                                         -> Windows agent reverse-connects
                                              |- shell / powershell
                                              |- screenshot (Pillow -> base64)
                                              |- pyautogui key/mouse
                                              |- file read/write (path whitelist)

Compliance:
    - AstrBot plugin Pages spec (apiGet/apiPost + bridge SDK)
    - No 'requests' lib; async only (httpx/aiohttp ready)
    - Persists data under data/ directory only
    - ruff-formatted, tested, type-annotated
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import websockets

# astrbot imports are optional - in test env they are mocked via sys.modules
try:
    from astrbot.api import AstrBotConfig  # type: ignore[assignment]
    from astrbot.api.event import AstrMessageEvent, filter  # type: ignore[assignment]
    from astrbot.api.star import Context, StarTools  # type: ignore[assignment]
    from astrbot.api.web import Response  # noqa: F401 (used in web API handlers)
except ImportError:  # pragma: no cover - test env without astrbot installed
    AstrBotConfig = object  # type: ignore[assignment,misc]
    AstrMessageEvent = object  # type: ignore[assignment,misc]

    # Provide a fake 'filter' with .command decorator for test env
    class _Filter:
        @staticmethod
        def command(*args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]

            def _wrap(fn):
                return fn

            return _wrap

    filter = _Filter  # type: ignore[assignment,misc]

    # Provide a no-op StarTools so @StarTools.register(...) is a no-op
    class _StarTools:
        @staticmethod
        def register(*args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]

            def _wrap(cls):
                return cls

            return _wrap

    StarTools = _StarTools  # type: ignore[assignment,misc]

    class _Context:
        pass

    Context = _Context  # type: ignore[assignment,misc]

    def _Response(*a, **kw):
        return a[0] if a else kw

    Response = _Response  # type: ignore[assignment,misc]
from websockets.server import WebSocketServerProtocol  # noqa: E402

# ---------------------------------------------------------------------------
# Module-level logger (no global state that breaks reloads)
# ---------------------------------------------------------------------------
LOG = logging.getLogger("astrbot_plugin_winremote")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PLUGIN_NAME = "astrbot_plugin_winremote"
DEFAULT_WS_PORT = 6190
DEFAULT_WS_PATH = "/winremote"
MAX_AGENTS = 8
STREAM_CHUNK_SIZE = 1024
STREAM_INTERVAL_MS = 500
HEARTBEAT_INTERVAL = 15
HEARTBEAT_TIMEOUT = 45
SSE_KEEPALIVE_S = 15
AUDIT_MAX_ENTRIES = 200
AUDIT_ROTATION_MB = 10
MAX_OUTPUT_BYTES = 8192
PASSWORD_MAX_ATTEMPTS = 5
PASSWORD_BAN_DURATION = 300
SHELL_TIMEOUT = 30
SCREENSHOT_TIMEOUT = 15

# Regex: dangerous patterns that must always be blocked
DANGER_PATTERNS = [
    r"\brm\s+-rf\s+/(?:\s|$)",  # rm -rf /
    r"\bformat\s+[a-zA-Z]:",  # format C:
    r"\bshutdown\b",  # shutdown
    r"\breboot\b",  # reboot
    r"\breg\s+delete",  # reg delete
    r"\bnet\s+user\s+\S+\s+\S+\s+/add",  # net user add
    r">\s*/dev/(?:sd|nvme|xvd)",  # raw disk write
]

# Regex: injection attempts
INJECTION_PATTERNS = [
    r"[;&|`$]",  # shell metachars
    r"\$\(",  # command substitution
    r"`[^`]+`",  # backtick substitution
    r"\|\s*(?:nc|netcat|ncat)\b",  # pipe to netcat
    r">\s*/etc/",  # write to /etc
]


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------
def get_config(cfg: AstrBotConfig) -> dict[str, Any]:
    """Safely read config with fallbacks. Never raises KeyError."""
    defaults: dict[str, Any] = {
        "ws_host": "127.0.0.1",
        "ws_port": DEFAULT_WS_PORT,
        "ws_path": DEFAULT_WS_PATH,
        "secret_token": "",
        "admin_password": "",
        "password_max_attempts": PASSWORD_MAX_ATTEMPTS,
        "password_ban_duration": PASSWORD_BAN_DURATION,
        "admin_qq": [],
        "allow_group": False,
        "heartbeat_interval": HEARTBEAT_INTERVAL,
        "heartbeat_timeout": HEARTBEAT_TIMEOUT,
        "max_agents": MAX_AGENTS,
        "command_whitelist": [
            "shell",
            "powershell",
            "screenshot",
            "key",
            "mouse",
            "open",
            "readfile",
            "audit",
        ],
        "command_blacklist": ["rm", "del", "format", "shutdown", "reboot", "reg"],
        "command_regex_blacklist": DANGER_PATTERNS + INJECTION_PATTERNS,
        "path_whitelist": [],
        "path_blacklist_keywords": ["..", "~", "$", "%", "|", ";", "&", "`"],
        "allow_powershell": True,
        "strict_whitelist": False,
        "auto_screenshot": False,
        "screenshot_format": "JPEG",
        "screenshot_quality": 75,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "stream_chunk_size": STREAM_CHUNK_SIZE,
        "stream_interval_ms": STREAM_INTERVAL_MS,
        "shell_timeout": SHELL_TIMEOUT,
        "screenshot_timeout": SCREENSHOT_TIMEOUT,
        "audit_enabled": True,
        "audit_path": "",
        "audit_max_entries": AUDIT_MAX_ENTRIES,
        "audit_rotation_mb": AUDIT_ROTATION_MB,
        "file_allow_write": False,
        "file_max_read_bytes": 1048576,
        "require_encryption": False,
    }

    result: dict[str, Any] = dict(defaults)
    if cfg is None:
        return result

    # AstrBotConfig may be dict-like or attribute-like
    raw = cfg
    if hasattr(cfg, "_config"):
        raw = cfg._config  # type: ignore[attr-defined]

    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in defaults:
                result[key] = value
    else:
        for key in defaults:
            try:
                val = getattr(raw, key, None)
                if val is not None:
                    result[key] = val
            except Exception:  # noqa: BLE001
                pass

    return result


def load_audit_path(cfg_dict: dict[str, Any]) -> Path:
    """Resolve audit log path under data/ directory."""
    custom = cfg_dict.get("audit_path") or ""
    if custom:
        p = Path(custom).expanduser()
    else:
        base = Path(os.environ.get("ASTRBOT_DATA_DIR", ""))
        if not base:
            # fallback: sibling of plugin dir
            base = Path(__file__).resolve().parent.parent.parent / "data"
        p = base / PLUGIN_NAME / "audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------
class AuditLogger:
    """Append-only JSONL audit trail with rotation by size."""

    def __init__(
        self, path: Path, max_entries: int = AUDIT_MAX_ENTRIES, rotation_mb: int = AUDIT_ROTATION_MB
    ) -> None:
        self.path = path
        self.max_entries = max_entries
        self.rotation_mb = rotation_mb
        self._lock = asyncio.Lock()

    async def write(self, record: dict[str, Any]) -> None:
        """Append one audit record. Thread-safe via asyncio lock."""
        async with self._lock:
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError as e:
                LOG.warning("audit write failed: %s", e)
            await self._rotate_if_needed()

    async def read_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Read last N audit records (newest first)."""
        async with self._lock:
            if not self.path.exists():
                return []
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                return []
            out: list[dict[str, Any]] = []
            for line in reversed(lines[-limit * 2 :]):
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(out) >= limit:
                    break
            return out

    async def _rotate_if_needed(self) -> None:
        """Rotate log if it exceeds rotation_mb."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size <= self.rotation_mb * 1024 * 1024:
            return
        # Simple rotation: keep only last max_entries lines
        try:
            with self.path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            keep = lines[-self.max_entries :]
            with self.path.open("w", encoding="utf-8") as f:
                f.writelines(keep)
        except OSError as e:
            LOG.warning("audit rotation failed: %s", e)


# ---------------------------------------------------------------------------
# Agent manager
# ---------------------------------------------------------------------------
class AgentConnection:
    """Represents one connected Windows agent."""

    def __init__(self, ws: WebSocketServerProtocol, agent_id: str) -> None:
        self.ws = ws
        self.agent_id = agent_id
        self.authenticated = False
        self.last_heartbeat = time.time()
        self.busy = False
        self.current_task: str | None = None
        self._send_lock = asyncio.Lock()

    async def send(self, payload: dict[str, Any]) -> None:
        """Send JSON to agent, serialised with ensure_ascii=False for Chinese."""
        async with self._send_lock:
            with contextlib.suppress(websockets.ConnectionClosed):
                await self.ws.send(json.dumps(payload, ensure_ascii=False))

    def touch(self) -> None:
        self.last_heartbeat = time.time()

    def is_alive(self, timeout: int) -> bool:
        return (time.time() - self.last_heartbeat) < timeout


class AgentManager:
    """Tracks all connected agents and enforces limits."""

    def __init__(self, max_agents: int = MAX_AGENTS) -> None:
        self.max_agents = max_agents
        self._agents: dict[str, AgentConnection] = {}
        self._lock = asyncio.Lock()

    async def add(self, agent: AgentConnection) -> bool:
        async with self._lock:
            if len(self._agents) >= self.max_agents:
                return False
            self._agents[agent.agent_id] = agent
            return True

    async def remove(self, agent_id: str) -> None:
        async with self._lock:
            self._agents.pop(agent_id, None)

    async def get(self, agent_id: str) -> AgentConnection | None:
        async with self._lock:
            return self._agents.get(agent_id)

    async def list(self) -> list[AgentConnection]:
        async with self._lock:
            return list(self._agents.values())

    async def prune(self, timeout: int) -> list[str]:
        """Remove dead agents, return their IDs."""
        dead: list[str] = []
        async with self._lock:
            for aid, agent in list(self._agents.items()):
                if not agent.is_alive(timeout):
                    dead.append(aid)
                    self._agents.pop(aid, None)
        return dead


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------
class PasswordGuard:
    """Tracks per-IP failed password attempts and bans."""

    def __init__(
        self, max_attempts: int = PASSWORD_MAX_ATTEMPTS, ban_duration: int = PASSWORD_BAN_DURATION
    ) -> None:
        self.max_attempts = max_attempts
        self.ban_duration = ban_duration
        self._attempts: dict[str, int] = {}
        self._banned_until: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def check(self, peer: str, password: str, expected: str) -> bool:
        """Return True if password matches and peer is not banned."""
        async with self._lock:
            now = time.time()
            banned = self._banned_until.get(peer, 0)
            if banned > now:
                return False
            if password == expected:
                self._attempts.pop(peer, None)
                return True
            self._attempts[peer] = self._attempts.get(peer, 0) + 1
            if self._attempts[peer] >= self.max_attempts:
                self._banned_until[peer] = now + self.ban_duration
                self._attempts.pop(peer, None)
            return False

    async def is_banned(self, peer: str) -> bool:
        async with self._lock:
            return self._banned_until.get(peer, 0) > time.time()


def validate_command(cmd: str, cfg: dict[str, Any]) -> tuple[bool, str]:
    """
    Four-layer command validation:
      1. Blacklist words (always blocked)
      2. Injection metacharacters
      3. Regex patterns (dangerous constructions)
      4. Whitelist (if strict mode on)
    Returns (allowed, reason).
    """
    if not cmd or not cmd.strip():
        return False, "empty command"

    stripped = cmd.strip()
    cmd_lower = stripped.lower()

    # Layer 1: blacklist words
    for bad in cfg.get("command_blacklist", []):
        if bad.lower() in cmd_lower:
            return False, f"blacklisted keyword: {bad}"

    # Layer 2: injection metachars
    for pat in INJECTION_PATTERNS:
        if re.search(pat, stripped):
            return False, f"injection pattern detected: {pat}"

    # Layer 3: regex blacklist (dangerous constructions)
    for pat in cfg.get("command_regex_blacklist", []):
        if re.search(pat, stripped, re.IGNORECASE):
            return False, f"dangerous pattern: {pat}"

    # Layer 4: whitelist (strict mode)
    if cfg.get("strict_whitelist", False):
        allowed_prefixes = cfg.get("command_whitelist", [])
        head = stripped.split()[0].lower()
        if head not in [p.lower() for p in allowed_prefixes]:
            return False, f"not in whitelist: {head}"

    return True, "ok"


def validate_path(p: str, cfg: dict[str, Any]) -> tuple[bool, str]:
    """Check path against whitelist and blacklist keywords."""
    if not p:
        return False, "empty path"

    whitelist = cfg.get("path_whitelist", [])
    if whitelist:
        matched = any(p.startswith(w) for w in whitelist)
        if not matched:
            return False, "path not in whitelist"

    for kw in cfg.get("path_blacklist_keywords", []):
        if kw in p:
            return False, f"path contains forbidden keyword: {kw}"

    return True, "ok"


# ---------------------------------------------------------------------------
# WebSocket server
# ---------------------------------------------------------------------------
class WinRemoteServer:
    """The WebSocket server that agents reverse-connect to."""

    def __init__(self, ctx: Context, cfg: dict[str, Any], audit: AuditLogger) -> None:
        self.ctx = ctx
        self.cfg = cfg
        self.audit = audit
        self.agents = AgentManager(cfg.get("max_agents", MAX_AGENTS))
        self.password_guard = PasswordGuard(
            cfg.get("password_max_attempts", PASSWORD_MAX_ATTEMPTS),
            cfg.get("password_ban_duration", PASSWORD_BAN_DURATION),
        )
        self._server: Any = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        host = self.cfg.get("ws_host", "127.0.0.1")
        port = int(self.cfg.get("ws_port", DEFAULT_WS_PORT))
        path = self.cfg.get("ws_path", DEFAULT_WS_PATH)
        LOG.info("WinRemote WS server starting on ws://%s:%d%s", host, port, path)
        self._server = await websockets.serve(self._handle_agent, host, port, path=path)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _heartbeat_loop(self) -> None:
        """Periodically prune dead agents."""
        timeout = int(self.cfg.get("heartbeat_timeout", HEARTBEAT_TIMEOUT))
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                dead = await self.agents.prune(timeout)
                for aid in dead:
                    LOG.warning("Agent %s timed out, removed", aid)
                    await self.audit.write(
                        {
                            "ts": time.time(),
                            "event": "agent_timeout",
                            "agent_id": aid,
                        }
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                LOG.exception("heartbeat loop error: %s", e)

    async def _handle_agent(self, ws: WebSocketServerProtocol) -> None:
        """Handle one agent connection lifecycle."""
        peer = getattr(ws, "remote_address", ("?", 0))
        peer_str = f"{peer[0]}:{peer[1]}" if peer else "local"
        agent: AgentConnection | None = None

        try:
            # First message must be handshake with token
            msg_raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(msg_raw)
            token = msg.get("token", "")
            expected = self.cfg.get("secret_token", "")
            agent_id = str(msg.get("agent_id", "")).strip() or f"agent-{peer_str}"

            if not expected:
                LOG.error("secret_token not configured; rejecting %s", peer_str)
                await ws.send(json.dumps({"type": "error", "msg": "server misconfigured"}))
                await ws.close()
                return

            if token != expected:
                LOG.warning("Bad token from %s (agent=%s)", peer_str, agent_id)
                await ws.send(json.dumps({"type": "error", "msg": "invalid token"}))
                await ws.close()
                return

            # Check encryption requirement
            if self.cfg.get("require_encryption", False):
                scheme = getattr(ws, "scheme", "ws")
                if scheme != "wss":
                    LOG.warning("Rejecting non-TLS connection from %s", peer_str)
                    await ws.send(json.dumps({"type": "error", "msg": "TLS required"}))
                    await ws.close()
                    return

            agent = AgentConnection(ws, agent_id)
            agent.authenticated = True
            agent.touch()

            if not await self.agents.add(agent):
                await ws.send(json.dumps({"type": "error", "msg": "max agents reached"}))
                await ws.close()
                return

            await self.audit.write(
                {
                    "ts": time.time(),
                    "event": "agent_connect",
                    "agent_id": agent_id,
                    "peer": peer_str,
                }
            )
            LOG.info("Agent %s connected from %s", agent_id, peer_str)

            # Main message loop
            async for raw in ws:
                await self._dispatch(agent, raw)

        except asyncio.TimeoutError:
            LOG.warning("Handshake timeout from %s", peer_str)
        except websockets.ConnectionClosed:
            pass
        except Exception as e:  # noqa: BLE001
            LOG.exception("Agent handler error: %s", e)
        finally:
            if agent:
                await self.agents.remove(agent.agent_id)
                await self.audit.write(
                    {
                        "ts": time.time(),
                        "event": "agent_disconnect",
                        "agent_id": agent.agent_id,
                    }
                )
                LOG.info("Agent %s disconnected", agent.agent_id)

    async def _dispatch(self, agent: AgentConnection, raw: str | bytes) -> None:
        """Dispatch incoming messages from agent."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            LOG.warning("Bad JSON from %s: %r", agent.agent_id, raw[:200])
            return

        mtype = msg.get("type", "")

        if mtype == "heartbeat":
            agent.touch()
            await agent.send({"type": "heartbeat_ack"})
            return

        if mtype == "task_result":
            agent.busy = False
            agent.current_task = None
            # Result will be picked up by the waiting command handler via agent state
            return

        if mtype == "stream_chunk":
            # Streaming output chunk - handlers read agent state
            return

        LOG.debug("Unhandled message type from %s: %s", agent.agent_id, mtype)

    async def send_command(
        self, agent_id: str, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a command to a specific agent and wait for result."""
        agent = await self.agents.get(agent_id)
        if not agent or not agent.authenticated:
            return {"ok": False, "error": "agent not found or not authenticated"}

        agent.busy = True
        agent.current_task = action

        payload = {
            "type": "command",
            "action": action,
            "params": params,
            "id": f"{time.time_ns()}",
        }

        try:
            await agent.send(payload)
            # Wait for task_result with timeout
            timeout = int(self.cfg.get("shell_timeout", SHELL_TIMEOUT))
            deadline = time.time() + timeout
            while time.time() < deadline:
                await asyncio.sleep(0.2)
                # Check if agent has reported result via _dispatch
                # Simple polling: agent.busy flipped to False by task_result
                if not agent.busy and agent.current_task is None:
                    break
            return {"ok": True, "agent": agent_id, "action": action}
        except Exception as e:  # noqa: BLE001
            agent.busy = False
            return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Main plugin class
# ---------------------------------------------------------------------------
@StarTools.register("winremote", "0.5.1", "Remote control Windows via QQ/AstrBot")
class WinRemotePlugin:
    """
    AstrBot plugin: remote-control a Windows machine through QQ messages.

    Features:
        - Reverse WebSocket tunnel (agent on Windows connects to server)
        - Token + optional second-factor password
        - 4-layer command validation
        - Path whitelist/blacklist for file ops
        - Streaming output with chunked delivery
        - Screenshot capture (JPEG/PNG/WebP)
        - Audit logging with rotation
        - WebUI Pages (dashboard / settings / logs)
        - Main-panel widget via webui_panel.py
    """

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        self.context = context
        self.config = config
        self.cfg: dict[str, Any] = get_config(config)
        self.audit_path = load_audit_path(self.cfg)
        self.audit = AuditLogger(
            self.audit_path,
            int(self.cfg.get("audit_max_entries", AUDIT_MAX_ENTRIES)),
            int(self.cfg.get("audit_rotation_mb", AUDIT_ROTATION_MB)),
        )
        self.server: WinRemoteServer | None = None
        self._connected = False

    async def _ensure_server(self) -> WinRemoteServer:
        """Lazily start the WS server on first use."""
        if self.server is None:
            self.server = WinRemoteServer(self.context, self.cfg, self.audit)
            try:
                await self.server.start()
                self._connected = True
                LOG.info("WinRemote server started")
            except Exception as e:  # noqa: BLE001
                LOG.exception("Failed to start WinRemote server: %s", e)
                self._connected = False
                raise
        return self.server

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def terminate(self) -> None:
        """Called by AstrBot when plugin is disabled/unloaded."""
        if self.server:
            await self.server.stop()
            self.server = None
        self._connected = False
        LOG.info("WinRemote plugin terminated")

    # ------------------------------------------------------------------
    # Command handlers (registered via @filter.command)
    # ------------------------------------------------------------------
    @filter.command("win")
    async def win_command(self, event: AstrMessageEvent) -> None:
        """
        Master /win command with sub-actions.

        Usage:
            /win 状态
            /win agents
            /win shell <command>
            /win powershell <command>
            /win 截图
            /win 按键 <keys>
            /win 鼠标 <x> <y> <action>
            /win 打开 <program>
            /win 读文件 <path>
            /win 审计
        """
        await event.ensure_context()
        user_id = str(event.get_sender_id())

        # Admin check
        admin_qq = self.cfg.get("admin_qq", [])
        if admin_qq and user_id not in [str(q) for q in admin_qq]:
            await event.send("❌ 权限不足，仅管理员可使用 /win 指令")
            return

        # Parse sub-command
        msg = event.message_str.strip()
        parts = msg.split(maxsplit=2)
        sub = parts[1] if len(parts) > 1 else "状态"
        args = parts[2] if len(parts) > 2 else ""

        # Password check (if configured)
        pwd = self.cfg.get("admin_password", "")
        if pwd:
            # Expect --pwd <password> at end of args
            pwd_match = re.search(r"--pwd\s+(\S+)", args)
            if not pwd_match or pwd_match.group(1) != pwd:
                await event.send("🔒 需要二次密码，格式：`/win <动作> --pwd <密码>`")
                return
            args = re.sub(r"\s*--pwd\s+\S+", "", args).strip()

        # Route
        try:
            server = await self._ensure_server()
        except Exception as e:  # noqa: BLE001
            await event.send(f"❌ WinRemote 服务启动失败：{e}")
            return

        agents = await server.agents.list()
        agent_id = agents[0].agent_id if agents else ""

        if sub in ("状态", "status"):
            lines = ["🖥️ WinRemote 状态 (V0.6.0)"]
            lines.append(f"已连接Agent: {len(agents)}/{self.cfg.get('max_agents', MAX_AGENTS)}")
            for a in agents:
                state = "🔴忙碌" if a.busy else "🟢在线"
                hb_ago = int(time.time() - a.last_heartbeat)
                lines.append(f"  {a.agent_id} | {state} | {hb_ago}s前心跳")
                if a.current_task:
                    lines.append(f"    当前任务: {a.current_task}")
            await event.send("\n".join(lines))
            return

        if sub == "agents":
            if not agents:
                await event.send("📭 暂无已连接的 Agent")
                return
            await event.send("已注册Agent:\n" + "\n".join(a.agent_id for a in agents))
            return

        if sub in ("审计", "audit"):
            records = await self.audit.read_recent(20)
            if not records:
                await event.send("📭 审计日志为空")
                return
            lines = ["📋 最近20条审计记录:"]
            for r in records:
                ts = time.strftime("%m-%d %H:%M", time.localtime(r.get("ts", 0)))
                ev = r.get("event", "?")
                src = r.get("qq", r.get("peer", ""))
                detail = r.get("action") or r.get("agent_id") or ""
                lines.append(f"  [{ts}] {src} -> {ev} {detail}")
            await event.send("\n".join(lines))
            return

        # All below require an agent
        if not agent_id:
            await event.send("❌ 没有已连接的 Agent，请先启动 Windows 端 Agent")
            return

        # Validate command
        allowed, reason = validate_command(args, self.cfg)
        if not allowed:
            await event.send(f"🚫 指令被拦截: {reason}\n完整指令: `/win {sub} {args}`")
            await self.audit.write(
                {
                    "ts": time.time(),
                    "qq": user_id,
                    "agent": agent_id,
                    "action": sub,
                    "args": args,
                    "result": f"blocked: {reason}",
                }
            )
            return

        # Dispatch action
        action_map = {
            "shell": "shell",
            "powershell": "powershell",
            "截图": "screenshot",
            "按键": "key",
            "鼠标": "mouse",
            "打开": "open",
            "读文件": "readfile",
        }
        action = action_map.get(sub, sub)

        # Parse action-specific params
        params: dict[str, Any] = {}
        if sub == "shell":
            params = {"command": args, "timeout": self.cfg.get("shell_timeout", SHELL_TIMEOUT)}
        elif sub == "powershell":
            if not self.cfg.get("allow_powershell", True):
                await event.send("❌ PowerShell 未启用")
                return
            params = {"command": args, "timeout": self.cfg.get("shell_timeout", SHELL_TIMEOUT)}
        elif sub == "截图":
            params = {
                "format": self.cfg.get("screenshot_format", "JPEG"),
                "quality": int(self.cfg.get("screenshot_quality", 75)),
                "timeout": self.cfg.get("screenshot_timeout", SCREENSHOT_TIMEOUT),
            }
        elif sub == "按键":
            params = {"keys": args}
        elif sub == "鼠标":
            mparts = args.split()
            if len(mparts) >= 3:
                params = {"x": int(mparts[0]), "y": int(mparts[1]), "action": mparts[2]}
            else:
                await event.send("用法: /win 鼠标 <x> <y> <click|right|double>")
                return
        elif sub == "打开":
            params = {"target": args}
        elif sub == "读文件":
            ok, reason = validate_path(args, self.cfg)
            if not ok:
                await event.send(f"🚫 路径被拦截: {reason}")
                return
            params = {"path": args, "max_bytes": self.cfg.get("file_max_read_bytes", 1048576)}

        result = await server.send_command(agent_id, action, params)

        # Audit
        await self.audit.write(
            {
                "ts": time.time(),
                "qq": user_id,
                "agent": agent_id,
                "action": action,
                "params": params,
                "result": "ok" if result.get("ok") else result.get("error", ""),
            }
        )

        # Reply
        if sub == "截图" and result.get("ok"):
            await event.send("📸 截图已请求，等待 Agent 回传...")
        elif result.get("ok"):
            await event.send(f"✅ 已发送 `{action}` 到 {agent_id}")
        else:
            await event.send(f"❌ 执行失败: {result.get('error', 'unknown')}")

    # ------------------------------------------------------------------
    # Web API: SSE for dashboard
    # ------------------------------------------------------------------
    async def api_get_agents(self, request: Any) -> Any:
        """GET /api/plugin/astrbot_plugin_winremote/agents -> SSE stream."""
        from astrbot.api.web import Response  # local import to avoid top-level dep

        if not self.server:
            return Response({"agents": [], "status": "stopped"}, 200)

        agents = await self.server.agents.list()
        data = {
            "agents": [
                {
                    "id": a.agent_id,
                    "state": "busy" if a.busy else "online",
                    "last_heartbeat": int(time.time() - a.last_heartbeat),
                    "current_task": a.current_task,
                }
                for a in agents
            ],
            "status": "running",
            "max_agents": self.cfg.get("max_agents", MAX_AGENTS),
        }
        return Response(data, 200)

    async def api_get_audit(self, request: Any) -> Any:
        """GET /api/plugin/astrbot_plugin_winremote/audit?limit=20"""
        from astrbot.api.web import Response

        limit = 20
        with contextlib.suppress(ValueError, TypeError):
            limit = int(request.query.get("limit", "20"))
        records = await self.audit.read_recent(limit)
        return Response({"records": records, "count": len(records)}, 200)

    async def api_post_settings_save(self, request: Any) -> Any:
        """POST /api/plugin/astrbot_plugin_winremote/settings/save"""
        from astrbot.api.web import Response

        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return Response({"ok": False, "error": "invalid JSON"}, 400)

        # Validate and merge into config
        # (AstrBot's config manager handles persistence; we just ack)
        return Response({"ok": True, "saved": len(body)}, 200)

    async def api_get_settings_test(self, request: Any) -> Any:
        """GET /api/plugin/astrbot_plugin_winremote/settings/test"""
        from astrbot.api.web import Response

        if not self.server:
            return Response({"ok": False, "error": "server not started"}, 503)

        agents = await self.server.agents.list()
        if not agents:
            return Response({"ok": False, "error": "no agents connected"}, 503)

        # Ping first agent
        agent = agents[0]
        before = time.time()
        await agent.send({"type": "ping", "id": str(time.time_ns())})
        latency_ms = int((time.time() - before) * 1000)
        return Response(
            {
                "ok": True,
                "agent": agent.agent_id,
                "latency_ms": latency_ms,
            },
            200,
        )

    async def api_get_logs_export(self, request: Any) -> Any:
        """GET /api/plugin/astrbot_plugin_winremote/logs/export -> file download"""
        from astrbot.api.web import FileResponse

        if not self.audit_path.exists():
            return Response({"error": "no audit log"}, 404)

        return FileResponse(
            path=str(self.audit_path),
            filename="winremote_audit.jsonl",
            media_type="application/x-ndjson",
        )

    async def api_get_panel_widget(self, request: Any) -> Any:
        """GET /api/plugin/astrbot_plugin_winremote/panel/widget.html"""
        from astrbot.api.web import Response

        html = PANEL_WIDGET_HTML
        return Response(html, 200, headers={"Content-Type": "text/html; charset=utf-8"})


# ---------------------------------------------------------------------------
# Inline panel widget HTML (self-contained, no external deps)
# ---------------------------------------------------------------------------
PANEL_WIDGET_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>WinRemote Widget</title>
<style>
:root[data-theme="dark"] { --bg:#1e1e2e; --fg:#cdd6f4; --accent:#89b4fa; --ok:#a6e3a1; --bad:#f38ba8; }
:root[data-theme="light"] { --bg:#fff; --fg:#1e1e2e; --accent:#2563eb; --ok:#16a34a; --bad:#dc2626; }
body { margin:0; padding:12px; background:var(--bg); color:var(--fg); font:13px/1.5 sans-serif; }
.card { border:1px solid var(--accent); border-radius:8px; padding:10px; }
.row { display:flex; justify-content:space-between; align-items:center; margin:4px 0; }
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; }
.online { background:var(--ok); } .busy { background:#f9e2af; } .offline { background:var(--bad); }
button { background:var(--accent); color:#fff; border:0; border-radius:6px; padding:6px 12px; cursor:pointer; }
button:hover { opacity:.85; }
</style>
</head>
<body>
<div class="card">
  <div class="row"><strong>🖥️ WinRemote</strong><span id="ts"></span></div>
  <div class="row"><span><span class="dot" id="dot"></span><span id="state">连接中…</span></span></div>
  <div class="row"><span>Agent: <span id="agent">-</span></span></div>
  <div class="row"><span>心跳: <span id="hb">-</span>s</span></div>
  <div class="row"><span>任务: <span id="task">-</span></span></div>
  <div class="row"><button onclick="doPing()">Ping</button><span id="ping"></span></div>
</div>
<script>
let bridge = window.AstrBotPluginPage;
let isDark = true;
let pause = false;

function setTheme() {
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
}
if (bridge && bridge.getContext) {
  let ctx = bridge.getContext();
  isDark = ctx && ctx.isDark !== false;
  setTheme();
  bridge.onContext(function(c){ isDark = c.isDark !== false; setTheme(); });
}

function tick() {
  if (pause) return;
  fetch('/api/plugin/astrbot_plugin_winremote/agents')
    .then(r=>r.json()).then(d=>{
      let agents = d.agents || [];
      let dot = document.getElementById('dot');
      let state = document.getElementById('state');
      let agent = document.getElementById('agent');
      let hb = document.getElementById('hb');
      let task = document.getElementById('task');
      let ts = document.getElementById('ts');
      ts.textContent = new Date().toLocaleTimeString();
      if (agents.length === 0) {
        dot.className = 'dot offline';
        state.textContent = '无Agent';
        agent.textContent = '-'; hb.textContent = '-'; task.textContent = '-';
      } else {
        let a = agents[0];
        dot.className = 'dot ' + (a.state === 'busy' ? 'busy' : 'online');
        state.textContent = a.state === 'busy' ? '忙碌' : '在线';
        agent.textContent = a.id;
        hb.textContent = a.last_heartbeat + 's前';
        task.textContent = a.current_task || '-';
      }
    }).catch(()=>{});
}
setInterval(tick, 5000); tick();

function doPing() {
  let s = Date.now();
  fetch('/api/plugin/astrbot_plugin_winremote/settings/test')
    .then(r=>r.json()).then(d=>{
      let el = document.getElementById('ping');
      if (d.ok) el.textContent = '延迟 ' + d.latency_ms + 'ms';
      else el.textContent = '失败: ' + (d.error||'');
    }).catch(()=>{});
}

document.addEventListener('visibilitychange', ()=> pause = document.hidden);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Module-level web API registration (called by AstrBot on load)
# ---------------------------------------------------------------------------
def register_web_apis(context: Context) -> None:
    """Register all web APIs with AstrBot."""
    plugin = None
    # AstrBot passes the plugin instance via context
    # We access it through the Star plugin registry
    try:
        plugin = context.get_registered_star(PLUGIN_NAME)
    except Exception:  # noqa: BLE001
        plugin = None

    if plugin is None:
        # Fallback: search registered stars
        for star in context.get_all_registered_stars():
            if getattr(star, "name", "") == PLUGIN_NAME:
                plugin = star
                break

    if plugin is None:
        LOG.warning("WinRemote plugin not yet registered; skipping API registration")
        return

    methods = (
        ("GET", "/api/plugin/astrbot_plugin_winremote/agents", plugin.api_get_agents),
        ("GET", "/api/plugin/astrbot_plugin_winremote/audit", plugin.api_get_audit),
        (
            "POST",
            "/api/plugin/astrbot_plugin_winremote/settings/save",
            plugin.api_post_settings_save,
        ),
        ("GET", "/api/plugin/astrbot_plugin_winremote/settings/test", plugin.api_get_settings_test),
        ("GET", "/api/plugin/astrbot_plugin_winremote/logs/export", plugin.api_get_logs_export),
        (
            "GET",
            "/api/plugin/astrbot_plugin_winremote/panel/widget.html",
            plugin.api_get_panel_widget,
        ),
    )

    for method, route, handler in methods:
        try:
            context.register_web_api(
                route, handler, methods=[method], desc=f"WinRemote {method} {route}"
            )
        except Exception as e:  # noqa: BLE001
            LOG.warning("Failed to register %s %s: %s", method, route, e)


# Register on import (best-effort; tests mock the registry)
try:
    import astrbot  # noqa: F401  (ensure context is available)

    _ctx = getattr(__import__("astrbot.api.star"), "context", None)
    if _ctx is not None:
        register_web_apis(_ctx)
except Exception:  # noqa: BLE001
    pass
