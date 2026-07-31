"""
tests/test_agent_protocol.py - V0.8.0
Tests for WinRemoteServer agent lifecycle, message dispatch, and panel data.
Each test builds its OWN server + FakeWS to avoid shared-state pollution.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import __init__ as plugin


# ---------------------------------------------------------------------------
# FakeWS — a proper async-iterable websocket simulator
# ---------------------------------------------------------------------------
class FakeWS:
    """Mimics a websocket: supports `async for x in ws` AND ws.recv()/send()/close()."""

    def __init__(self, messages, peer=("127.0.0.1", 50000)):
        self._msgs = list(messages)
        self._idx = 0
        self.sent = []
        self.remote_address = peer
        self.secure = False

    def __aiter__(self):
        # Synchronous: return self (which has __anext__)
        return self

    async def __anext__(self):
        if self._idx >= len(self._msgs):
            raise StopAsyncIteration
        val = self._msgs[self._idx]
        self._idx += 1
        return val

    async def recv(self):
        if self._idx >= len(self._msgs):
            raise plugin.websockets.exceptions.ConnectionClosed(None, None)
        val = self._msgs[self._idx]
        self._idx += 1
        return val

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fresh_cfg(**overrides):
    """Return a deep-copied default config with optional overrides."""
    cfg = copy.deepcopy(plugin.get_config(None))
    cfg.update(overrides)
    return cfg


async def make_server(cfg, tmp_path, ctx=None):
    """Create and start a server with a fake websockets.serve."""
    if ctx is None:
        ctx = MagicMock()
    audit = plugin.AuditLogger(tmp_path / "audit.jsonl")
    srv = plugin.WinRemoteServer(ctx, cfg, audit)

    async def fake_serve(handler, host, port, path=None, **kw):
        fake = MagicMock()
        fake.close = AsyncMock()
        fake.wait_closed = AsyncMock()
        fake_serve.handler = handler
        return fake

    with patch.object(plugin.websockets, "serve", side_effect=fake_serve):
        await srv.start()

    return srv, fake_serve


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------
class TestAgentLifecycle:
    async def test_handshake_success(self, tmp_path):
        cfg = fresh_cfg(secret_token="test-token")
        srv, _ = await make_server(cfg, tmp_path)

        ws = FakeWS(
            [
                json.dumps({"type": "handshake", "token": "test-token", "agent_id": "agent-A"}),
                json.dumps({"type": "heartbeat"}),
            ]
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        # Proof: heartbeat_ack was sent → handshake succeeded
        sent_strs = [str(s) for s in ws.sent]
        assert any("heartbeat_ack" in s for s in sent_strs), f"Expected heartbeat_ack in {ws.sent}"
        await srv.stop()

    async def test_handshake_bad_token(self, tmp_path):
        cfg = fresh_cfg(secret_token="right-token")
        srv, _ = await make_server(cfg, tmp_path)

        ws = FakeWS(
            [json.dumps({"type": "handshake", "token": "wrong", "agent_id": "agent-B"})],
            peer=("10.0.0.2", 50001),
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        # Agent-B must NOT be registered
        agents = await srv.agents.list()
        assert all(a.agent_id != "agent-B" for a in agents)
        sent_strs = [str(s) for s in ws.sent]
        assert any("invalid" in s.lower() for s in sent_strs)
        await srv.stop()

    async def test_handshake_no_token_configured(self, tmp_path):
        cfg = fresh_cfg(secret_token="")  # empty → misconfigured
        srv, _ = await make_server(cfg, tmp_path)

        ws = FakeWS(
            [json.dumps({"type": "handshake", "token": "anything", "agent_id": "agent-C"})],
            peer=("10.0.0.3", 50002),
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        sent_strs = [str(s) for s in ws.sent]
        assert any("misconfig" in s.lower() for s in sent_strs)
        await srv.stop()

    async def test_heartbeat_keeps_alive(self, tmp_path):
        cfg = fresh_cfg(secret_token="tok")
        srv, _ = await make_server(cfg, tmp_path)

        ws = FakeWS(
            [
                json.dumps({"type": "handshake", "token": "tok", "agent_id": "hb-agent"}),
                json.dumps({"type": "heartbeat"}),
            ]
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        sent_strs = [str(s) for s in ws.sent]
        assert any("heartbeat_ack" in s for s in sent_strs)
        await srv.stop()

    async def test_max_agents_enforced(self, tmp_path):
        cfg = fresh_cfg(secret_token="tok", max_agents=1)
        ctx = MagicMock()
        audit = plugin.AuditLogger(tmp_path / "a.jsonl")
        srv = plugin.WinRemoteServer(ctx, cfg, audit)

        existing = plugin.AgentConnection(ws=MagicMock(), agent_id="already-there")
        await srv.agents.add(existing)

        ws = FakeWS([json.dumps({"type": "handshake", "token": "tok", "agent_id": "rejected-one"})])
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        agents = await srv.agents.list()
        assert len(agents) == 1
        assert agents[0].agent_id == "already-there"
        await srv.stop()


# ---------------------------------------------------------------------------
# Message dispatch
# ---------------------------------------------------------------------------
class TestDispatch:
    async def test_heartbeat_ack(self, tmp_path):
        cfg = fresh_cfg(secret_token="tok")
        srv, _ = await make_server(cfg, tmp_path)

        ws = FakeWS(
            [
                json.dumps({"type": "handshake", "token": "tok", "agent_id": "disp-1"}),
                json.dumps({"type": "heartbeat"}),
            ]
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        sent_strs = [str(s) for s in ws.sent]
        assert any("heartbeat_ack" in s for s in sent_strs)
        await srv.stop()

    async def test_invalid_json_ignored(self, tmp_path):
        cfg = fresh_cfg(secret_token="tok")
        srv, _ = await make_server(cfg, tmp_path)

        ws = FakeWS(
            [
                json.dumps({"type": "handshake", "token": "tok", "agent_id": "disp-2"}),
                "this is not json {{",
                json.dumps({"type": "heartbeat"}),
            ]
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        # Invalid JSON is ignored, heartbeat still acked
        sent_strs = [str(s) for s in ws.sent]
        assert any("heartbeat_ack" in s for s in sent_strs)
        await srv.stop()


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------
class TestPruning:
    async def test_prune_dead(self, tmp_path):
        cfg = fresh_cfg(secret_token="tok")
        ctx = MagicMock()
        audit = plugin.AuditLogger(tmp_path / "p.jsonl")
        srv = plugin.WinRemoteServer(ctx, cfg, audit)

        alive = plugin.AgentConnection(ws=MagicMock(), agent_id="alive-one")
        dead = plugin.AgentConnection(ws=MagicMock(), agent_id="dead-one")
        dead.last_heartbeat -= 1000

        await srv.agents.add(alive)
        await srv.agents.add(dead)

        dead_ids = await srv.agents.prune(timeout=15)
        assert "dead-one" in dead_ids
        assert "alive-one" not in dead_ids
        await srv.stop()


# ---------------------------------------------------------------------------
# Panel data endpoint
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        if isinstance(body, (str, bytes)):
            self.body = body
        else:
            self.body = json.dumps(body)
        self.status_code = status
        self.headers = headers or {}


class TestPanelData:
    async def test_no_server_returns_stopped(self, tmp_path):
        from webui_panel import get_panel_data

        fake_req = MagicMock()
        with patch("webui_panel.Response", FakeResponse, create=True):
            resp = await get_panel_data(fake_req)
        body = json.loads(resp.body)
        assert body["status"] == "stopped"
        assert body["agents"] == []

    async def test_with_agents(self, tmp_path):
        from webui_panel import get_panel_data

        cfg = fresh_cfg()
        ctx = MagicMock()
        audit = plugin.AuditLogger(tmp_path / "pd.jsonl")
        srv = plugin.WinRemoteServer(ctx, cfg, audit)

        agent = plugin.AgentConnection(ws=MagicMock(), agent_id="panel-agent")
        agent.busy = True
        agent.current_task = "shell ipconfig"
        await srv.agents.add(agent)

        fake_plugin = MagicMock()
        fake_plugin.server = srv
        fake_plugin.cfg = cfg
        with (
            patch("webui_panel._get_plugin", return_value=fake_plugin),
            patch("webui_panel.Response", FakeResponse, create=True),
        ):
            fake_req = MagicMock()
            resp = await get_panel_data(fake_req)

        body = json.loads(resp.body)
        assert body["status"] == "running"
        assert len(body["agents"]) == 1
        assert body["agents"][0]["id"] == "panel-agent"
        assert body["agents"][0]["state"] == "busy"
        assert body["agents"][0]["current_task"] == "shell ipconfig"
        await srv.stop()


# ---------------------------------------------------------------------------
# send_command
# ---------------------------------------------------------------------------
class TestSendCommand:
    async def test_unknown_agent(self, tmp_path):
        cfg = fresh_cfg()
        ctx = MagicMock()
        audit = plugin.AuditLogger(tmp_path / "sc.jsonl")
        srv = plugin.WinRemoteServer(ctx, cfg, audit)

        result = await srv.send_command("nonexistent", "shell", {"command": "ls"})
        assert result["ok"] is False
        assert "not found" in result["error"].lower()
        await srv.stop()

    async def test_sends_and_waits(self, tmp_path):
        cfg = fresh_cfg()
        ctx = MagicMock()
        audit = plugin.AuditLogger(tmp_path / "sc2.jsonl")
        srv = plugin.WinRemoteServer(ctx, cfg, audit)

        ws = MagicMock()
        agent = plugin.AgentConnection(ws=ws, agent_id="send-agent")
        agent.authenticated = True
        await srv.agents.add(agent)

        sent_payloads = []

        async def fake_send(payload):
            sent_payloads.append(json.loads(payload))
            agent.busy = False
            agent.current_task = None

        ws.send = AsyncMock(side_effect=fake_send)

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await srv.send_command("send-agent", "shell", {"command": "ls"})

        assert result["ok"] is True, f"unexpected result: {result}"
        assert "id" in result, f"expected 'id' in result, got {result}"
        assert len(sent_payloads) >= 1
        assert sent_payloads[0]["type"] == "command"
        assert sent_payloads[0]["action"] == "shell"
        await srv.stop()


# ---------------------------------------------------------------------------
# Handshake errors (additional coverage)
# ---------------------------------------------------------------------------
class TestHandshakeErrors:
    async def test_missing_token_rejected(self, tmp_path):
        cfg = fresh_cfg(secret_token="")  # misconfigured
        ctx = MagicMock()
        audit = plugin.AuditLogger(tmp_path / "ht.jsonl")
        srv = plugin.WinRemoteServer(ctx, cfg, audit)

        async def fake_serve(handler, host, port, **kw):
            fake = MagicMock()
            fake.close = AsyncMock()
            fake.wait_closed = AsyncMock()
            fake_serve.handler = handler
            return fake

        with patch.object(plugin.websockets, "serve", side_effect=fake_serve):
            await srv.start()

        ws = FakeWS(
            [
                json.dumps({"token": "", "agent_id": "x"}),
            ],
            peer=("10.0.0.1", 50010),
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        assert ws.sent, "Expected server to send at least one message"
        sent_strs = [str(s) for s in ws.sent]
        assert any("misconfig" in s.lower() for s in sent_strs)
        await srv.stop()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
