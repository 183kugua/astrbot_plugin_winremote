"""
webui_panel.py - V0.9.0
AstrBot WebUI main-panel widget for WinRemote.

Exposes:
    GET /api/plugin/astrbot_plugin_winremote/panel/widget.html
    GET /api/plugin/astrbot_plugin_winremote/panel/data.json (SSE-ready JSON)

The widget is self-contained (no external deps), theme-aware, and
pauses SSE polling when the browser tab is hidden.
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

PLUGIN_NAME = "astrbot_plugin_winremote"


# ---------------------------------------------------------------------------
# Backend: JSON data endpoint (SSE-ready)
# ---------------------------------------------------------------------------
async def get_panel_data(request: Any) -> Response:
    """Return current agent snapshot as JSON."""
    # The plugin instance is reachable through the star registry
    plugin = _get_plugin()
    if plugin is None or plugin.server is None:
        return Response(
            json.dumps({"agents": [], "status": "stopped", "ts": time.time()}),
            200,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    agents = await plugin.server.agents.list()
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
        "max_agents": plugin.cfg.get("max_agents", 8),
        "ts": time.time(),
    }
    return Response(
        json.dumps(data),
        200,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


# ---------------------------------------------------------------------------
# Backend: widget HTML
# ---------------------------------------------------------------------------
WIDGET_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>WinRemote</title>
<style>
:root[data-theme="dark"]  { --bg:#1e1e2e; --fg:#cdd6f4; --accent:#89b4fa; --ok:#a6e3a1; --warn:#f9e2af; --bad:#f38ba8; --card:#181825; }
:root[data-theme="light"] { --bg:#ffffff; --fg:#1e1e2e; --accent:#2563eb; --ok:#16a34a; --warn:#d97706; --bad:#dc2626; --card:#f8fafc; }
* { box-sizing:border-box; }
body { margin:0; padding:14px; background:var(--bg); color:var(--fg); font:13px/1.5 system-ui,sans-serif; }
.card { background:var(--card); border:1px solid var(--accent); border-radius:10px; padding:12px 14px; }
h3 { margin:0 0 8px; font-size:14px; color:var(--accent); }
.row { display:flex; justify-content:space-between; align-items:center; padding:3px 0; }
.dot { width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:6px; vertical-align:middle; }
.online { background:var(--ok); } .busy { background:var(--warn); } .offline { background:var(--bad); }
button { background:var(--accent); color:#fff; border:0; border-radius:6px; padding:5px 12px; cursor:pointer; font-size:12px; }
button:hover { opacity:.85; }
#ping { font-size:12px; margin-left:8px; color:var(--fg); opacity:.8; }
.meta { font-size:11px; opacity:.6; margin-top:6px; }
</style>
</head>
<body>
<div class="card">
  <h3>🖥️ WinRemote 远控面板</h3>
  <div class="row"><span><span class="dot" id="dot"></span><span id="state">连接中…</span></span></div>
  <div class="row"><span>Agent：<span id="agent">-</span></span></div>
  <div class="row"><span>心跳：<span id="hb">-</span></span></div>
  <div class="row"><span>任务：<span id="task">-</span></span></div>
  <div class="row"><button onclick="doPing()">Ping</button><span id="ping"></span></div>
  <div class="meta" id="ts"></div>
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
  fetch('/api/plugin/astrbot_plugin_winremote/panel/data.json')
    .then(r => r.json()).then(d => {
      let dot = document.getElementById('dot');
      let st  = document.getElementById('state');
      let ag  = document.getElementById('agent');
      let hb  = document.getElementById('hb');
      let tk  = document.getElementById('task');
      let ts  = document.getElementById('ts');
      ts.textContent = new Date().toLocaleTimeString();
      if (!d.agents || d.agents.length === 0) {
        dot.className = 'dot offline';
        st.textContent = '无 Agent';
        ag.textContent = '-'; hb.textContent = '-'; tk.textContent = '-';
      } else {
        let a = d.agents[0];
        dot.className = 'dot ' + (a.state === 'busy' ? 'busy' : 'online');
        st.textContent = a.state === 'busy' ? '忙碌' : '在线';
        ag.textContent = a.id;
        hb.textContent = a.last_heartbeat + 's 前';
        tk.textContent = a.current_task || '-';
      }
    }).catch(()=>{});
}
setInterval(tick, 5000); tick();

function doPing() {
  let t0 = Date.now();
  fetch('/api/plugin/astrbot_plugin_winremote/settings/test')
    .then(r => r.json()).then(d => {
      let el = document.getElementById('ping');
      el.textContent = d.ok ? '延迟 ' + d.latency_ms + 'ms' : '失败:' + (d.error||'');
    }).catch(()=>{});
}

document.addEventListener('visibilitychange', () => { pause = document.hidden; });
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
    except Exception:  # noqa: BLE001
        return None

    try:
        return _ctx.get_registered_star(PLUGIN_NAME)
    except Exception:  # noqa: BLE001
        pass

    try:
        for star in _ctx.get_all_registered_stars():
            if getattr(star, "name", "") == PLUGIN_NAME:
                return star
    except Exception:  # noqa: BLE001
        pass

    return None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register_web_apis(context: Any) -> None:
    """Register panel endpoints with AstrBot."""
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
    )
    for method, route, handler in methods:
        try:
            context.register_web_api(
                route,
                handler,
                methods=[method],
                desc=f"WinRemote panel {method} {route}",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("WinRemote panel: register %s failed: %s", route, e)


# Auto-register on import (best-effort; tests mock the registry)
try:
    from astrbot.api.star import context as _ctx  # type: ignore[import-not-found]

    if _ctx is not None:
        register_web_apis(_ctx)
except Exception:  # noqa: BLE001
    pass
