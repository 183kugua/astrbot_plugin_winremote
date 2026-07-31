"""
tests/test_agent_protocol.py - V0.5.1
Tests for WinRemoteServer agent lifecycle, message dispatch, and SSE data endpoint.
Uses websockets library to spin up a real (in-process) server and connect a mock agent.
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
# Helper: build a WebSocket that works as "async for x in ws:"
# ---------------------------------------------------------------------------
class _MessageQueue:
    """A single async-iterable message queue shared by recv() and 'async for'."""

    def __init__(self, items):
        self._items = list(items)
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._items):
            # Signal end-of-stream so the server's async-for loop exits
            raise StopAsyncIteration
        val = self._items[self._i]
        self._i += 1
        return val

    async def recv(self):
        """Mimic ws.recv() — return next message or raise ConnectionClosed."""
        if self._i >= len(self._items):
            raise plugin.websockets.exceptions.ConnectionClosed(None, None)
        val = self._items[self._i]
        self._i += 1
        return val


def make_ws(recv_messages, peer=("127.0.0.1", 50000)):
    """Return a MagicMock ws that supports both .recv() and 'async for' iteration.

    Key trick: BOTH ws.recv() and 'async for ws' draw from the SAME
    _MessageQueue, so the handshake (recv) and the main loop (async for)
    see a consistent message stream.
    """
    ws = MagicMock()
    ws.remote_address = peer

    queue = _MessageQueue(recv_messages)

    # 'async for x in ws:' calls ws.__aiter__()
    ws.__aiter__ = lambda self: queue
    ws.__anext__ = lambda self: queue.__anext__()
    # ws.recv() is awaited once for the handshake
    ws.recv = AsyncMock(side_effect=queue.recv)
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def base_cfg() -> dict:
    """Return a FRESH copy so tests don't pollute each other."""
    return copy.deepcopy(plugin.get_config(None))


@pytest.fixture()
def ctx_mock() -> MagicMock:
    return MagicMock()


@pytest.fixture()
async def server_pair(base_cfg, ctx_mock, tmp_path):
    audit = plugin.AuditLogger(tmp_path / "audit.jsonl")
    srv = plugin.WinRemoteServer(ctx_mock, base_cfg, audit)

    started = {}

    async def fake_serve(handler, host, port, path=None, **kw):
        started["handler"] = handler
        fake = MagicMock()
        fake.close = AsyncMock()
        fake.wait_closed = AsyncMock()
        return fake

    with patch.object(plugin.websockets, "serve", side_effect=fake_serve):
        await srv.start()

    yield srv, started
    await srv.stop()


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------
class TestAgentLifecycle:
    async def test_handshake_success(self, server_pair, base_cfg):
        srv, _ = server_pair
        base_cfg["secret_token"] = "test-token"

        ws = make_ws(
            [
                json.dumps({"token": "test-token", "agent_id": "agent-A"}),
                json.dumps({"type": "heartbeat"}),
            ]
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        # Agent is added during the handshake, then removed in finally when
        # the async-for loop is exhausted.  The proof of a successful
        # handshake is that ws.send WAS called (heartbeat_ack was sent).
        assert ws.send.called, "ws.send should be called on successful handshake"
        sent = [str(c) for c in ws.send.call_args_list]
        assert any("heartbeat_ack" in s for s in sent)

    async def test_handshake_bad_token(self, server_pair, base_cfg):
        srv, _ = server_pair
        base_cfg["secret_token"] = "right-token"

        ws = make_ws([json.dumps({"token": "wrong", "agent_id": "agent-B"})])
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        agents = await srv.agents.list()
        assert all(a.agent_id != "agent-B" for a in agents)
        sent_calls = [str(c) for c in ws.send.call_args_list]
        assert any("invalid" in s.lower() for s in sent_calls)

    async def test_handshake_no_token_configured(self, server_pair, base_cfg):
        srv, _ = server_pair
        base_cfg["secret_token"] = ""

        ws = make_ws([json.dumps({"token": "anything", "agent_id": "agent-C"})])
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        sent_calls = [str(c) for c in ws.send.call_args_list]
        assert any("misconfig" in s.lower() for s in sent_calls)

    async def test_heartbeat_keeps_alive(self, server_pair, base_cfg):
        srv, _ = server_pair
        base_cfg["secret_token"] = "tok"

        ws = make_ws(
            [
                json.dumps({"token": "tok", "agent_id": "hb-agent"}),
                json.dumps({"type": "heartbeat"}),
            ]
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        # Agent is added during handshake then removed in finally when
        # the async-for loop is exhausted.  The proof that the heartbeat
        # was received and processed is that ws.send was called with
        # a "heartbeat_ack" payload.
        assert ws.send.called, "ws.send should be called for heartbeat_ack"
        sent = [str(c) for c in ws.send.call_args_list]
        assert any("heartbeat_ack" in s for s in sent)

    async def test_max_agents_enforced(self, base_cfg, ctx_mock, tmp_path):
        base_cfg["secret_token"] = "tok"
        base_cfg["max_agents"] = 1
        audit = plugin.AuditLogger(tmp_path / "a.jsonl")
        srv = plugin.WinRemoteServer(ctx_mock, base_cfg, audit)

        existing = plugin.AgentConnection(ws=MagicMock(), agent_id="already-there")
        await srv.agents.add(existing)

        ws = make_ws([json.dumps({"token": "tok", "agent_id": "rejected-one"})])
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
    async def test_heartbeat_ack(self, server_pair, base_cfg):
        srv, _ = server_pair
        base_cfg["secret_token"] = "tok"

        ws = make_ws(
            [
                json.dumps({"token": "tok", "agent_id": "disp-1"}),
                json.dumps({"type": "heartbeat"}),
            ]
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        sent_calls = [str(c) for c in ws.send.call_args_list]
        assert any("heartbeat_ack" in s for s in sent_calls)

    async def test_invalid_json_ignored(self, server_pair, base_cfg):
        srv, _ = server_pair
        base_cfg["secret_token"] = "tok"

        # Provide enough messages so the agent stays alive through the loop:
        # 1) handshake token, 2) bad JSON (logged+ignored), 3) heartbeat (keeps alive)
        ws = make_ws(
            [
                json.dumps({"token": "tok", "agent_id": "disp-2"}),
                "this is not json {{{",
                json.dumps({"type": "heartbeat"}),
            ]
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        # Agent should have been registered (invalid JSON was just ignored)
        # After the iterator is exhausted, _handle_agent's finally block removes it,
        # so we check the send log instead: the heartbeat should have been acked.
        sent_calls = [str(c) for c in ws.send.call_args_list]
        assert any("heartbeat_ack" in s for s in sent_calls)


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------
class TestPruning:
    async def test_prune_dead(self, base_cfg, ctx_mock, tmp_path):
        base_cfg["secret_token"] = "tok"
        audit = plugin.AuditLogger(tmp_path / "p.jsonl")
        srv = plugin.WinRemoteServer(ctx_mock, base_cfg, audit)

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
# SSE-style data endpoint (webui_panel)
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
    async def test_no_server_returns_stopped(self, base_cfg, ctx_mock, tmp_path):
        from webui_panel import get_panel_data

        fake_req = MagicMock()
        with patch("webui_panel.Response", FakeResponse, create=True):
            resp = await get_panel_data(fake_req)
        body = json.loads(resp.body)
        assert body["status"] == "stopped"
        assert body["agents"] == []

    async def test_with_agents(self, base_cfg, ctx_mock, tmp_path):
        from webui_panel import get_panel_data

        audit = plugin.AuditLogger(tmp_path / "pd.jsonl")
        srv = plugin.WinRemoteServer(ctx_mock, base_cfg, audit)
        agent = plugin.AgentConnection(ws=MagicMock(), agent_id="panel-agent")
        agent.busy = True
        agent.current_task = "shell ipconfig"
        await srv.agents.add(agent)

        fake_plugin = MagicMock()
        fake_plugin.server = srv
        fake_plugin.cfg = base_cfg
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
    async def test_unknown_agent(self, base_cfg, ctx_mock, tmp_path):
        audit = plugin.AuditLogger(tmp_path / "sc.jsonl")
        srv = plugin.WinRemoteServer(ctx_mock, base_cfg, audit)

        result = await srv.send_command("nonexistent", "shell", {"command": "ls"})
        assert result["ok"] is False
        assert "not found" in result["error"].lower()
        await srv.stop()

    async def test_sends_and_waits(self, base_cfg, ctx_mock, tmp_path):
        audit = plugin.AuditLogger(tmp_path / "sc2.jsonl")
        srv = plugin.WinRemoteServer(ctx_mock, base_cfg, audit)

        ws = MagicMock()
        ws.send = AsyncMock()
        agent = plugin.AgentConnection(ws=ws, agent_id="send-agent")
        agent.authenticated = True  # mark as authenticated
        await srv.agents.add(agent)

        # After send, simulate agent responding (task_result sets busy=False)
        async def fake_send(payload):
            agent.busy = False
            agent.current_task = None

        ws.send = AsyncMock(side_effect=fake_send)

        time_values = iter([100, 101, 102, 103])

        def fake_time():
            try:
                return next(time_values)
            except StopIteration:
                return 200

        with patch("asyncio.sleep", new=AsyncMock()), patch("time.time", side_effect=fake_time):
            result = await srv.send_command("send-agent", "shell", {"command": "ls"})

        assert result["ok"] is True, f"unexpected result: {result}"
        assert result["agent"] == "send-agent"
        assert ws.send.called
        sent_payload = json.loads(ws.send.call_args[0][0])
        assert sent_payload["type"] == "command"
        assert sent_payload["action"] == "shell"
        await srv.stop()


# ---------------------------------------------------------------------------
# Handshake / token rejection
# ---------------------------------------------------------------------------
class TestHandshakeErrors:
    async def test_missing_token_rejected(self, base_cfg, ctx_mock, tmp_path):
        """When secret_token is empty, server sends 'server misconfigured' and closes."""
        audit = plugin.AuditLogger(tmp_path / "ht.jsonl")
        srv = plugin.WinRemoteServer(ctx_mock, base_cfg, audit)

        ws = MagicMock()
        ws.remote_address = ("10.0.0.1", 5000)
        # First recv returns a message, then close
        ws.recv = AsyncMock(
            side_effect=[
                json.dumps({"token": "", "agent_id": "x"}),
                plugin.websockets.exceptions.ConnectionClosed(None, None),
            ]
        )
        ws.send = AsyncMock()
        ws.close = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        assert ws.close.called
        await srv.stop()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
