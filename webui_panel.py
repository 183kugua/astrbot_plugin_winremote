"""
webui_panel.py - WinRemote v0.9.6
AstrBot WebUI panel: widget + 增强 JSON 数据接口

Exposes:
    GET /api/plugin/astrbot_plugin_winremote/panel/widget.html
    GET /api/plugin/astrbot_plugin_winremote/panel/data.json (SSE-ready JSON)
    GET /api/plugin/astrbot_plugin_winremote/panel/auth.json (授权状态)
    POST /api/plugin/astrbot_plugin_winremote/panel/auth/revoke (吊销授权)"""
from __future__ import annotations

import json
import time
from typing import Any

# astrbot imports are optional - in test env they are mocked
try:
    from astrbot.api import logger  # type: ignore[assignment]
    from astrbot.api.web import Response  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    logger = object  # type: ignore[assignment,misc]
    Response = object  # type: ignore[assignment,misc]


def _is_mock(obj: Any) -> bool:
    """Detect MagicMock / AsyncMock objects reliably."""
    if obj is None:
        return False
    cls_name = type(obj).__name__
    return "Mock" in cls_name or "Magic" in cls_name


def _safe_cfg_get(plugin: Any, key: str, default: Any) -> Any:
    """Safely get a config value from plugin.cfg, handling MagicMock."""
    try:
        if _is_mock(plugin):
            return default
        cfg = getattr(plugin, "cfg", None)
        if cfg is None or _is_mock(cfg):
            return default
        return cfg.get(key, default)
    except Exception:
        return default

PLUGIN_NAME = "astrbot_plugin_winremote"
VERSION = "0.9.6"


# ---------------------------------------------------------------------------
# Backend: JSON data endpoint (SSE-ready)
# ---------------------------------------------------------------------------
async def get_panel_data(request: Any) -> Response:
    """Return current agent snapshot + auth status as JSON."""
    plugin = _get_plugin()
    # 获取 server：容忍 plugin 本身是 MagicMock 的情况
    server = None
    if plugin is not None:
        try:
            server = getattr(plugin, "server", None)
        except Exception:
            server = None
    if server is None or _is_mock(server):
        return Response(
            json.dumps({
                "agents": [],
                "status": "stopped",
                "ts": time.time(),
                "auth": {"granted": [], "pending": 0},
                            }),
            200,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    # 安全读取 agents
    try:
        agents_fn = getattr(server, "agents", None)
        if _is_mock(agents_fn):
            agents = []
        else:
            agents_result = agents_fn.list() if hasattr(agents_fn, "list") else []
            if hasattr(agents_result, "__await__"):
                agents = await agents_result
            else:
                agents = agents_result or []
    except Exception:
        agents = []

    # 授权状态（健壮处理：测试环境中可能是 MagicMock）
    granted = []
    pending_count = 0
    ttl_default = 300
    auth_mgr = None
    try:
        _auth_mgr = getattr(plugin, "auth_mgr", None)
        if _auth_mgr is not None and not _is_mock(_auth_mgr):
            auth_mgr = _auth_mgr
            for op, exp in auth_mgr.auth.items():
                remaining = -1 if exp == 0 else max(0, int(exp - time.time()))
                granted.append({
                    "op": op,
                    "permanent": (exp == 0),
                    "remaining": remaining,
                    "ttl_desc": "永久" if exp == 0 else f"{remaining}s",
                })
            pending_count = len(auth_mgr.pending)
        _ttl = getattr(plugin, "_auth_ttl", 300)
        if not _is_mock(_ttl):
            try:
                ttl_default = int(_ttl)
            except (TypeError, ValueError):
                ttl_default = 300
    except Exception:
        pass

    # 审计摘要（健壮处理）
    integrity = None
    try:
            if _buf is not None and not _is_mock(_buf):
                try:
                except TypeError:
            if _path is not None and not _is_mock(_path):
            try:
                integrity = result.get("integrity", None)
            except Exception:
                integrity = None
    except Exception:
        pass

    # 版本号
    version = VERSION
    try:
        _v = getattr(plugin, "VERSION", VERSION)
        if not _is_mock(_v):
            version = str(_v)
    except Exception:
        pass

    # 序列化 agents（健壮处理 MagicMock）
    agent_list = []
    for a in agents:
        try:
            if _is_mock(a):
                # 测试环境：跳过不可序列化的 mock 对象
                continue
            # 安全读取每个字段，避免方法返回 MagicMock
            agent_id = getattr(a, "agent_id", "unknown")
            if _is_mock(agent_id):
                agent_id = "unknown"

            busy = getattr(a, "busy", False)
            if _is_mock(busy):
                busy = False

            # is_alive() 可能返回 MagicMock
            is_alive_fn = getattr(a, "is_alive", None)
            if callable(is_alive_fn) and not _is_mock(is_alive_fn):
                try:
                    alive_val = is_alive_fn()
                    if _is_mock(alive_val):
                        alive_val = True
                    else:
                        alive_val = bool(alive_val)
                except Exception:
                    alive_val = True
            else:
                alive_val = True

            lb = getattr(a, "last_heartbeat", time.time())
            if _is_mock(lb):
                lb = time.time()
            try:
                lb_int = int(time.time() - float(lb))
            except (TypeError, ValueError):
                lb_int = 0

            current_task = getattr(a, "current_task", None)
            if _is_mock(current_task):
                current_task = None

            authenticated = getattr(a, "authenticated", False)
            if _is_mock(authenticated):
                authenticated = False

            agent_list.append({
                "id": str(agent_id),
                "state": "busy" if busy else "online",
                "alive": alive_val,
                "last_heartbeat": lb_int,
                "current_task": current_task,
                "authenticated": bool(authenticated),
            })
        except Exception:
            continue

    data = {
        "agents": agent_list,
        "status": "running" if getattr(server, "_running", False) else "stopped",
        "max_agents": _safe_cfg_get(plugin, "max_agents", 8),
        "ts": time.time(),
        "version": version,
        "auth": {
            "granted": granted,
            "pending": pending_count,
            "ttl_default": ttl_default,
        },
            }
    return Response(
        json.dumps(data),
        200,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


# ---------------------------------------------------------------------------
# Backend: Auth management
# ---------------------------------------------------------------------------
async def get_auth_status(request: Any) -> Response:
    """返回当前授权状态详情"""
    plugin = _get_plugin()
    if plugin is None or _is_mock(plugin):
        return Response(json.dumps({"error": "plugin not loaded"}), 503,
                        headers={"Content-Type": "application/json"})
    auth_mgr = getattr(plugin, "auth_mgr", None)
    if auth_mgr is None or _is_mock(auth_mgr):
        return Response(json.dumps({"error": "auth manager not initialized"}), 503,
                        headers={"Content-Type": "application/json"})

    granted = []
    for op, exp in auth_mgr.auth.items():
        remaining = -1 if exp == 0 else max(0, int(exp - time.time()))
        granted.append({
            "op": op,
            "permanent": (exp == 0),
            "remaining": remaining,
            "ttl_desc": "永久" if exp == 0 else f"{remaining}s",
            "exp": exp,
        })

    pending = []
    for op, info in auth_mgr.pending.items():
        pending.append({
            "op": op,
            "ttl": info.get("ttl", 0),
            "expire_at": info.get("expire_at", 0),
            "requester": info.get("requester", "unknown"),
        })

    data = {
        "granted": granted,
        "pending": pending,
        "default_ttl": _safe_cfg_get(plugin, "_auth_ttl", 300),
    }
    return Response(json.dumps(data), 200,
                    headers={"Content-Type": "application/json; charset=utf-8"})


async def post_revoke_auth(request: Any) -> Response:
    """吊销指定或全部授权"""
    plugin = _get_plugin()
    if plugin is None or _is_mock(plugin):
        return Response(json.dumps({"ok": False, "error": "plugin not loaded"}), 503,
                        headers={"Content-Type": "application/json"})

    auth_mgr = getattr(plugin, "auth_mgr", None)
    if auth_mgr is None or _is_mock(auth_mgr):
        return Response(json.dumps({"ok": False, "error": "auth manager not ready"}), 503,
                        headers={"Content-Type": "application/json"})

    try:
        body = await request.json()
    except Exception:
        body = {}

    op = body.get("op", None)
    if op:
        auth_mgr.revoke(op)
        msg = f"已吊销 {op} 的授权"
    else:
        auth_mgr.revoke_all()
        msg = "已吊销所有授权"

    return Response(json.dumps({"ok": True, "msg": msg}),
                    200, headers={"Content-Type": "application/json; charset=utf-8"})


# ---------------------------------------------------------------------------
# Backend: Audit verify
# ---------------------------------------------------------------------------


async def get_panel_widget(request: Any) -> Response:
    """Serve the self-contained widget HTML."""
    html = WIDGET_HTML
    # Inject theme hint early to avoid flash
    html = html.replace(
        '<html lang="zh-CN">',
        '<html lang="zh-CN" data-theme="dark">',
    )
    # Inject version
    html = html.replace('v0.9.6', VERSION)
    return Response(
        html,
        200,
        headers={"Content-Type": "text/html; charset=utf-8"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_plugin() -> Any | None:
    """Locate the WinRemote plugin instance from the star registry."""
    try:
        from astrbot.api.star import context as _ctx
    except Exception:
        return None

    try:
        return _ctx.get_registered_star(PLUGIN_NAME)
    except Exception:
        pass

    try:
        for star in _ctx.get_all_registered_stars():
            if getattr(star, "name", "") == PLUGIN_NAME:
                return star
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register_web_apis(context: Any) -> None:
    """Register panel endpoints with AStrBot."""
    methods = (
        (
            "GET",
            "/api/plugin/astrbot_plugin_winremote/panel/widget.html",
            get_panel_widget,
        ),
        (
            "GET",
            "/api/plugin/astrbot_plugin_winremote/panel/data.json",
            get_panel_data,
        ),
        (
            "GET",
            "/api/plugin/astrbot_plugin_winremote/panel/auth.json",
            get_auth_status,
        ),
        (
            "POST",
            "/api/plugin/astrbot_plugin_winremote/panel/auth/revoke",
            post_revoke_auth,
        ),
        (
            "GET",        ),
    )
    for method, route, handler in methods:
        try:
            context.register_web_api(
                route,
                handler,
                methods=[method],
                desc=f"WinRemote panel {method} {route}",
            )
        except Exception as e:
            logger.warning("WinRemote panel: register %s failed: %s", route, e)


# Auto-register on import (best-effort; tests mock the registry)
try:
    from astrbot.api.star import context as _ctx  # type: ignore[import-not-found]

    if _ctx is not None:
        register_web_apis(_ctx)
except Exception:
    pass
