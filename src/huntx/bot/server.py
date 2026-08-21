"""Real-Time WebSocket & Telemetry Broadcaster.

Authority:
    RFC 6455 (The WebSocket Protocol): https://datatracker.ietf.org/doc/html/rfc6455
"""
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Set

@dataclass
class TelemetryEvent:
    """Structured telemetry broadcast event."""
    event_type: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "payload": self.payload
        }

class TelemetryServer:
    """Async event broadcaster managing active WebSocket subscribers."""

    def __init__(self):
        self.active_clients: Set[asyncio.Queue] = set()

    def register_client(self, queue: asyncio.Queue) -> None:
        """Subscribe client message queue to telemetry broadcasts."""
        self.active_clients.add(queue)

    def unregister_client(self, queue: asyncio.Queue) -> None:
        """Remove client from active broadcast set."""
        self.active_clients.discard(queue)

    async def broadcast(self, event: TelemetryEvent) -> None:
        """Fan out telemetry payload to all active client queues."""
        msg = event.to_dict()
        for q in list(self.active_clients):
            try:
                await q.put(msg)
            except Exception:
                self.unregister_client(q)
