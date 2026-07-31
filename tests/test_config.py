"""
tests/test_config.py - V0.5.1
Tests for configuration loading, command/path validation, and audit logger.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make plugin importable when running pytest from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import __init__ as plugin  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def default_cfg() -> dict:
    """Fresh copy of default config."""
    return plugin.get_config(None)


@pytest.fixture()
def tmp_audit_path(tmp_path: Path) -> Path:
    return tmp_path / "audit.jsonl"


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------
class TestGetConfig:
    def test_returns_defaults_when_none(self, default_cfg: dict) -> None:
        assert default_cfg["ws_port"] == 6190
        assert default_cfg["secret_token"] == ""
        assert default_cfg["command_whitelist"] == [
            "shell",
            "powershell",
            "screenshot",
            "key",
            "mouse",
            "open",
            "readfile",
            "audit",
        ]
        assert default_cfg["require_encryption"] is False

    def test_dict_input_merges(self) -> None:
        cfg = plugin.get_config({"secret_token": "abc123", "ws_port": 9999})
        assert cfg["secret_token"] == "abc123"
        assert cfg["ws_port"] == 9999
        # Untouched key keeps default
        assert cfg["max_agents"] == 8

    def test_unknown_key_ignored(self) -> None:
        cfg = plugin.get_config({"not_a_real_key": 42})
        assert "not_a_real_key" not in cfg

    def test_attribute_like_input(self, monkeypatch: pytest.Monkeypatch) -> None:
        """Simulate AstrBotConfig object with attributes via _config dict."""
        fake = MagicMock()
        fake._config = {"secret_token": "tok", "ws_port": 1234, "onexist": "x"}
        cfg = plugin.get_config(fake)
        assert cfg["secret_token"] == "tok"
        assert cfg["ws_port"] == 1234
        assert "onexist" not in cfg


# ---------------------------------------------------------------------------
# validate_command
# ---------------------------------------------------------------------------
class TestValidateCommand:
    def test_empty_command(self, default_cfg: dict) -> None:
        ok, reason = plugin.validate_command("", default_cfg)
        assert ok is False
        assert "empty" in reason

    def test_simple_whitelisted(self, default_cfg: dict) -> None:
        ok, reason = plugin.validate_command("shell ipconfig", default_cfg)
        assert ok is True

    def test_blacklist_rm(self, default_cfg: dict) -> None:
        ok, reason = plugin.validate_command("shell rm -rf /", default_cfg)
        assert ok is False
        # blacklist hits before injection check
        assert "blacklist" in reason

    def test_injection_semicolon(self, default_cfg: dict) -> None:
        # "rm" is in command_blacklist, so it gets caught as blacklist first.
        # Use a command without blacklisted words to test injection detection.
        ok, reason = plugin.validate_command("shell ls; cat /etc/passwd", default_cfg)
        assert ok is False
        assert "injection" in reason

    def test_injection_backtick(self, default_cfg: dict) -> None:
        ok, reason = plugin.validate_command("shell `whoami`", default_cfg)
        assert ok is False

    def test_strict_whitelist_rejects(self, default_cfg: dict) -> None:
        cfg = {**default_cfg, "strict_whitelist": True}
        # "shell" is in whitelist, so this should pass
        ok, reason = plugin.validate_command("shell ls", cfg)
        assert ok is True
        # But "curl" is not
        ok2, _ = plugin.validate_command("curl http://evil", cfg)
        assert ok2 is False

    def test_regex_dangerous_rm_root(self, default_cfg: dict) -> None:
        ok, reason = plugin.validate_command("shell rm -rf /", default_cfg)
        assert ok is False


# ---------------------------------------------------------------------------
# validate_path
# ---------------------------------------------------------------------------
class TestValidatePath:
    def test_empty(self, default_cfg: dict) -> None:
        ok, reason = plugin.validate_path("", default_cfg)
        assert ok is False

    def test_whitelist_match(self, default_cfg: dict) -> None:
        cfg = {**default_cfg, "path_whitelist": ["C:\\Temp", "D:\\Work"]}
        ok, _ = plugin.validate_path("C:\\Temp\\a.txt", cfg)
        assert ok is True
        ok2, _ = plugin.validate_path("C:\\Other\\b.txt", cfg)
        assert ok2 is False

    def test_blacklist_keyword(self, default_cfg: dict) -> None:
        cfg = {**default_cfg, "path_whitelist": ["C:\\"]}
        ok, reason = plugin.validate_path("C:\\..\\passwd", cfg)
        assert ok is False
        assert "forbidden" in reason

    def test_no_whitelist_passes(self, default_cfg: dict) -> None:
        ok, _ = plugin.validate_path("C:\\anything.txt", default_cfg)
        assert ok is True


# ---------------------------------------------------------------------------
# PasswordGuard
# ---------------------------------------------------------------------------
class TestPasswordGuard:
    async def _make_guard(self) -> plugin.PasswordGuard:
        return plugin.PasswordGuard(max_attempts=3, ban_duration=60)

    async def test_correct_password(self) -> None:
        g = await self._make_guard()
        ok = await g.check("1.2.3.4", "secret", "secret")
        assert ok is True
        assert await g.is_banned("1.2.3.4") is False

    async def test_wrong_password_then_ban(self) -> None:
        g = await self._make_guard()
        for _ in range(3):
            await g.check("5.6.7.8", "wrong", "secret")
        banned = await g.is_banned("5.6.7.8")
        assert banned is True

    async def test_reset_on_success(self) -> None:
        g = await self._make_guard()
        await g.check("9.9.9.9", "wrong", "secret")
        await g.check("9.9.9.9", "secret", "secret")
        # After success, attempts should be cleared
        assert "9.9.9.9" not in g._attempts


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------
class TestAuditLogger:
    async def test_write_and_read(self, tmp_audit_path: Path) -> None:
        al = plugin.AuditLogger(tmp_audit_path, max_entries=10, rotation_mb=1)
        await al.write({"event": "test", "qq": "123"})
        await al.write({"event": "test2", "qq": "456"})
        records = await al.read_recent(limit=10)
        assert len(records) == 2
        events = [r["event"] for r in records]
        assert "test2" in events
        assert "test" in events

    async def test_read_empty(self, tmp_audit_path: Path) -> None:
        al = plugin.AuditLogger(tmp_audit_path)
        records = await al.read_recent(limit=5)
        assert records == []

    async def test_invalid_json_line_skipped(self, tmp_audit_path: Path) -> None:
        tmp_audit_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_audit_path.write_text('{not valid json\n{"event":"ok"}', encoding="utf-8")
        al = plugin.AuditLogger(tmp_audit_path)
        records = await al.read_recent(limit=10)
        assert len(records) == 1
        assert records[0]["event"] == "ok"


# ---------------------------------------------------------------------------
# AgentConnection
# ---------------------------------------------------------------------------
class TestAgentConnection:
    def test_is_alive(self, default_cfg: dict) -> None:
        agent = plugin.AgentConnection(ws=MagicMock(), agent_id="test-1")
        agent.last_heartbeat = __import__("time").time() - 5
        assert agent.is_alive(timeout=15) is True
        agent.last_heartbeat = __import__("time").time() - 100
        assert agent.is_alive(timeout=15) is False

    def test_touch_updates_heartbeat(self) -> None:
        agent = plugin.AgentConnection(ws=MagicMock(), agent_id="test-2")
        old = agent.last_heartbeat
        __import__("time").sleep(0.01)
        agent.touch()
        assert agent.last_heartbeat > old


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
