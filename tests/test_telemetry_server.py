# Tests for Real-Time WebSocket Telemetry Server
import pytest
import asyncio
from huntx.bot.server import TelemetryServer, TelemetryEvent


@pytest.mark.asyncio
async def test_telemetry_server_broadcaster():
    server = TelemetryServer()

    async def mock_client_queue():
        q = asyncio.Queue()
        server.register_client(q)
        return q

    q = await mock_client_queue()
    event = TelemetryEvent(
        event_type="NODE_PING",
        payload={"node_id": "DE-01", "ping_ms": 38.5, "country": "DE"}
    )
    await server.broadcast(event)

    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["event_type"] == "NODE_PING"
    assert msg["payload"]["node_id"] == "DE-01"

    server.unregister_client(q)
    assert len(server.active_clients) == 0
