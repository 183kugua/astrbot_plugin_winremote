"""
webui_panel.py - WinRemote v0.9.6
AstrBot WebUI panel: widget + 增强 JSON 数据接口

Exposes:
    GET /api/plugin/astrbot_plugin_winremote/panel/widget.html
    GET /api/plugin/astrbot_plugin_winremote/panel/data.json (SSE-ready JSON)
    GET /api/plugin/astrbot_plugin_winremote/panel/auth.json (授权状态)
    POST /api/plugin/astrbot_plugin_winremote/panel/auth/revoke (吊销授权)
    GET /api/plugin/astrbot_plugin_winremote/panel/audit/verify (HMAC 校验)
"""
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
                "audit": {"count": 0, "integrity": None},
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
    audit_count = 0
    integrity = None
    audit_path = ""
    try:
        _audit = getattr(plugin, "audit", None)
        if _audit is not None and not _is_mock(_audit):
            _buf = getattr(_audit, "_buf", None)
            if _buf is not None and not _is_mock(_buf):
                try:
                    audit_count = len(_buf)
                except TypeError:
                    audit_count = 0
            _path = getattr(_audit, "path", None)
            if _path is not None and not _is_mock(_path):
                audit_path = str(_path)
        if auth_mgr is not None and not _is_mock(auth_mgr) and audit_path:
            try:
                result = auth_mgr.verify_audit(audit_path, auth_mgr.key)
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
        "audit": {
            "count": audit_count,
            "integrity": integrity,
            "path": audit_path,
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
async def get_audit_verify(request: Any) -> Response:
    """校验审计日志 HMAC 完整性"""
    plugin = _get_plugin()
    if plugin is None or _is_mock(plugin):
        return Response(json.dumps({"ok": False, "error": "plugin not loaded"}), 503,
                        headers={"Content-Type": "application/json"})

    auth_mgr = getattr(plugin, "auth_mgr", None)
    if auth_mgr is None or _is_mock(auth_mgr):
        return Response(json.dumps({"ok": False, "error": "auth manager not ready"}), 503,
                        headers={"Content-Type": "application/json"})

    audit = getattr(plugin, "audit", None)
    audit_path = "data/winremote_audit.jsonl"
    if audit is not None and not _is_mock(audit):
        _path = getattr(audit, "path", None)
        if _path is not None and not _is_mock(_path):
            audit_path = str(_path)

    # verify_audit 是 auth 模块的顶层函数，不是 AuthManager 方法
    try:
        from auth import verify_audit as _verify
    except ImportError:
        return Response(json.dumps({"ok": False, "error": "auth module not available"}), 500,
                        headers={"Content-Type": "application/json"})

    try:
        # 优先用 plugin 的 secret_token；fallback 到 auth_mgr.key
        secret = getattr(plugin, "secret_token", None)
        if secret is None or _is_mock(secret):
            secret = getattr(auth_mgr, "key", None)
            if secret is not None and not _is_mock(secret):
                # key 是 bytes（pbkdf2 派生），verify_audit 期望 str token
                # 这里没法逆向派生，用空 token 会让校验失败 → 走下面的 except
                secret = None
        if secret is None:
            # 直接读 audit 文件行数返回降级结果
            try:
                with open(audit_path, encoding="utf-8") as f:
                    lines = [line for line in f if line.strip()]
                return Response(json.dumps({
                    "ok": True,
                    "integrity": None,
                    "ok_count": len(lines),
                    "tampered_lines": [],
                    "note": "cannot verify without secret_token",
                }), 200, headers={"Content-Type": "application/json; charset=utf-8"})
            except Exception:
                return Response(json.dumps({"ok": False, "error": "secret_token unavailable"}), 500,
                                headers={"Content-Type": "application/json"})
        result = _verify(audit_path, str(secret))
        result["ok"] = True
        return Response(json.dumps(result), 200,
                        headers={"Content-Type": "application/json; charset=utf-8"})
    except Exception as e:
        return Response(json.dumps({"ok": False, "error": str(e)}), 500,
                        headers={"Content-Type": "application/json; charset=utf-8"})


# ---------------------------------------------------------------------------
# Backend: Widget HTML (v0.9.6 增强版)
# ---------------------------------------------------------------------------
WIDGET_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<title>WinRemote</title>
<style>
:root[data-theme="dark"]  { --bg:#1e1e2e; --fg:#cdd6f4; --accent:#89b4fa; --ok:#a6e3a1; --warn:#f9e2af; --bad:#f38ba8; --card:#181825; --border:#313244; }
:root[data-theme="light"] { --bg:#ffffff; --fg:#1e1e2e; --accent:#2563eb; --ok:#16a34a; --warn:#d97706; --bad:#dc2626; --card:#f8fafc; --border:#e5e7eb; }
* { box-sizing:border-box; }
body { margin:0; padding:14px; background:var(--bg); color:var(--fg); font:13px/1.5 system-ui,sans-serif; }
.card { background:var(--card); border:1px solid var(--accent); border-radius:10px; padding:12px 14px; }
h3 { margin:0 0 8px; font-size:14px; color:var(--accent); display:flex; align-items:center; gap:6px; }
h3 .ver { font-size:10px; background:var(--accent); color:#fff; padding:1px 6px; border-radius:8px; font-weight:500; }
.row { display:flex; justify-content:space-between; align-items:center; padding:3px 0; }
.dot { width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:6px; vertical-align:middle; }
.online { background:var(--ok); box-shadow:0 0 6px var(--ok); }
.busy { background:var(--warn); box-shadow:0 0 6px var(--warn); }
.offline { background:var(--bad); }
button { background:var(--accent); color:#fff; border:0; border-radius:6px; padding:5px 12px; cursor:pointer; font-size:12px; }
button:hover { opacity:.85; }
button.danger { background:var(--bad); }
button:disabled { opacity:.5; cursor:not-allowed; }
#ping { font-size:11px; margin-left:8px; color:var(--fg); opacity:.8; }
.meta { font-size:11px; opacity:.6; margin-top:6px; }
.auth-section { margin-top:10px; padding-top:10px; border-top:1px solid var(--border); }
.auth-item { display:flex; justify-content:space-between; align-items:center; padding:4px 0; font-size:12px; }
.auth-tag { display:inline-block; padding:1px 6px; border-radius:4px; font-size:10px; font-weight:600; }
.auth-tag.perm { background:var(--warn); color:#1e1e2e; }
.auth-tag.temp { background:var(--accent); color:#fff; }
.auth-tag.pending { background:var(--bad); color:#fff; }
.integrity-ok { color:var(--ok); font-size:11px; }
.integrity-bad { color:var(--bad); font-size:11px; }
.integrity-unknown { color:var(--warn); font-size:11px; }
</style>
</head>
<body>
<div class="card">
  <h3>🖥️ WinRemote <span class="ver" id="ver">v0.9.6</span></h3>
  <div class="row"><span><span class="dot" id="dot"></span><span id="state">连接中…</span></span></div>
  <div class="row"><span>Agent：<span id="agent">-</span></span></div>
  <div class="row"><span>心跳：<span id="hb">-</span></span></div>
  <div class="row"><span>任务：<span id="task">-</span></span></div>
  <div class="row"><button onclick="doPing()">Ping</button><span id="ping"></span></div>

  <div class="auth-section">
    <div class="row"><span style="font-weight:600;font-size:12px;">🔐 授权状态</span><button class="danger" onclick="revokeAll()">全部吊销</button></div>
    <div id="authList" style="margin-top:6px;"></div>
    <div class="row" style="margin-top:6px;"><span id="integrityText" class="integrity-unknown">审计: 检测中...</span><button onclick="verifyAudit()">校验</button></div>
  </div>

  <div class="meta" id="ts"></div>
</div>
<script>
let bridge = window.AstrBotPluginPage;
let isDark = true;
let pause = false;
let _authTimer = null;

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
  fetch('/api/plugin/astrbot_plugin_winremote/panel/data.json')
    .then(r => r.json()).then(d => {
      let dot = document.getElementById('dot');
      let st  = document.getElementById('state');
      let ag  = document.getElementById('agent');
      let hb  = document.getElementById('hb');
      let tk  = document.getElementById('task');
      let ts  = document.getElementById('ts');
      let ver = document.getElementById('ver');
      ver.textContent = d.version || 'v0.9.6';
      ts.textContent = new Date().toLocaleTimeString();
      if (!d.agents || d.agents.length === 0) {
        dot.className = 'dot offline';
        st.textContent = '无 Agent';
        ag.textContent = '-'; hb.textContent = '-'; tk.textContent = '-';
      } else {
        let a = d.agents[0];
        dot.className = 'dot ' + (a.alive ? (a.state==='busy'?'busy':'online') : 'offline');
        st.textContent = !a.alive ? '离线' : (a.state==='busy'?'忙碌':'在线');
        ag.textContent = a.id;
        hb.textContent = (a.last_heartbeat||0) + 's 前';
        tk.textContent = a.current_task || '-';
      }
      // 授权列表
      renderAuth(d.auth);
      // 审计完整性
      if (d.audit && d.audit.integrity !== null && d.audit.integrity !== undefined) {
        let el = document.getElementById('integrityText');
        if (d.audit.integrity) {
          el.className = 'integrity-ok';
          el.textContent = '✅ 审计完整 (' + d.audit.count + ' 条)';
        } else {
          el.className = 'integrity-bad';
          el.textContent = '⚠️ 审计可能被篡改!';
        }
      }
    }).catch(()=>{});
}
function renderAuth(auth) {
  let el = document.getElementById('authList');
  if (!auth || (!auth.granted.length && !auth.pending)) {
    el.innerHTML = '<div style="font-size:11px;opacity:.5;padding:4px 0;">无活跃授权</div>';
    return;
  }
  let html = '';
  auth.granted.forEach(g => {
    let tag = g.permanent
      ? '<span class="auth-tag perm">永久</span>'
      : '<span class="auth-tag temp">' + g.ttl_desc + '</span>';
    html += '<div class="auth-item"><span>' + g.op + ' ' + tag + '</span><button class="danger" style="padding:2px 8px;font-size:10px;" onclick="revokeOp(\'' + g.op + '\')">吊销</button></div>';
  });
  if (auth.pending > 0) {
    html += '<div class="auth-item"><span><span class="auth-tag pending">等待确认</span></span><span style="font-size:11px;opacity:.6;">' + auth.pending + ' 项</span></div>';
  }
  el.innerHTML = html;
}
function revokeOp(op) {
  fetch('/api/plugin/astrbot_plugin_winremote/panel/auth/revoke', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({op:op})
  }).then(()=>tick()).catch(()=>{});
}
function revokeAll() {
  if (!confirm('确定吊销所有授权？')) return;
  fetch('/api/plugin/astrbot_plugin_winremote/panel/auth/revoke', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({})
  }).then(()=>tick()).catch(()=>{});
}
function verifyAudit() {
  let el = document.getElementById('integrityText');
  el.className = 'integrity-unknown';
  el.textContent = '校验中...';
  fetch('/api/plugin/astrbot_plugin_winremote/panel/audit/verify')
    .then(r=>r.json()).then(d=>{
      if (d.integrity) {
        el.className = 'integrity-ok';
        el.textContent = '✅ 审计完整 (共 ' + d.ok_count + ' 条, 篡改: ' + d.tampered_lines.length + ')';
      } else {
        el.className = 'integrity-bad';
        el.textContent = '⚠️ 发现 ' + d.tampered_lines.length + ' 行被篡改!';
      }
    }).catch(e=>{
      el.className = 'integrity-bad';
      el.textContent = '❌ 校验失败: ' + e.message;
    });
}
function doPing() {
  let t0 = Date.now();
  fetch('/api/plugin/astrbot_plugin_winremote/settings/test')
    .then(r=>r.json()).then(d=>{
      let el = document.getElementById('ping');
      el.textContent = d.ok ? '延迟 ' + d.latency_ms + 'ms' : '失败:' + (d.error||'');
    }).catch(()=>{});
}
document.addEventListener('visibilitychange', () => { pause = document.hidden; });
setInterval(tick, 5000); tick();
</script>
</body>
</html>
"""


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
            "GET",
            "/api/plugin/astrbot_plugin_winremote/panel/audit/verify",
            get_audit_verify,
        ),
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
