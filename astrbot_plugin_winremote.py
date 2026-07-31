"""
astrbot_plugin_winremote - V0.7.0
AstrBot plugin entry point.

AstrBot's loader looks for either:
  - main.py, or
  - <plugin_dir_name>.py

This file is the latter. It re-exports the public API from
the internal package (__init__.py) so AstrBot can discover
@StarTools.register'd classes and @filter.command handlers.
"""

from __future__ import annotations

# Module-level logger
import logging

# Re-export everything from the internal package
from .__init__ import (  # noqa: F401
    AUDIT_MAX_ENTRIES,
    AUDIT_ROTATION_MB,
    DANGER_PATTERNS,
    DEFAULT_WS_PATH,
    DEFAULT_WS_PORT,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    INJECTION_PATTERNS,
    MAX_AGENTS,
    MAX_OUTPUT_BYTES,
    PANEL_WIDGET_HTML,
    PASSWORD_BAN_DURATION,
    PASSWORD_MAX_ATTEMPTS,
    PLUGIN_NAME,
    SCREENSHOT_TIMEOUT,
    SHELL_TIMEOUT,
    SSE_KEEPALIVE_S,
    STREAM_CHUNK_SIZE,
    STREAM_INTERVAL_MS,
    AgentConnection,
    AgentManager,
    AuditLogger,
    PasswordGuard,
    WinRemotePlugin,
    WinRemoteServer,
    get_config,
    load_audit_path,
    register_web_apis,
    validate_command,
    validate_path,
)

LOG = logging.getLogger("astrbot_plugin_winremote")
