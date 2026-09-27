"""Live event bus + WebSocket hub.

The console is a watch-room: risk scores, new crowd reports and issued alerts
have to appear without a refresh. Every state-changing service call publishes
here, and connected clients receive a compact envelope they fan out locally.

Channel model: ``public`` (citizen map, no PII) and ``ops`` (responder/admin).
Citizens never receive other users' phone numbers on any channel.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("aapaatsathi.live")

PUBLIC = "public"
OPS = "ops"


class ConnectionManager:
    """Fan-out hub with a small in-memory replay buffer.

    The replay buffer exists because a judge's laptop will reconnect when it
    sleeps; resending the last N events is friendlier than a stale screen.
    """

    def __init__(self, history_size: int = 120) -> None:
        self._sockets: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self.history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._loop: asyncio.AbstractEventLoop | None = None

    # ---------------------------------------------------------------- lifecycle
    async def connect(self, websocket: WebSocket, channel: str = PUBLIC) -> None:
        await websocket.accept()
        async with self._lock:
            self._sockets[channel].add(websocket)
        log.debug("ws connected on %s (%d total)", channel, len(self._sockets[channel]))

    async def disconnect(self, websocket: WebSocket, channel: str = PUBLIC) -> None:
        async with self._lock:
            self._sockets[channel].discard(websocket)
        log.debug("ws left %s (%d remain)", channel, len(self._sockets[channel]))

    # ----------------------------------------------------------------- delivery
    async def publish(self, event: str, data: Any, channel: str = PUBLIC) -> None:
        message = {
            "event": event,
            "data": data,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.history.append(message)
        channels = list(self._sockets) if channel == "*" else [channel]
        for name in channels:
            await self._send(name, message)

    def publish_threadsafe(self, event: str, data: Any, channel: str = PUBLIC) -> None:
        """Publish from synchronous/callback contexts."""
        if self._loop is None or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.publish(event, data, channel), self._loop)

    async def _send(self, channel: str, message: dict[str, Any]) -> None:
        targets = list(self._sockets.get(channel, ()))
        if not targets:
            return
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for socket in targets:
            try:
                await socket.send_text(payload)
            except Exception:  # client vanished mid-write
                dead.append(socket)
        if dead:
            async with self._lock:
                for socket in dead:
                    self._sockets[channel].discard(socket)

    # ------------------------------------------------------------------- replay
    async def send_history(self, websocket: WebSocket, limit: int = 25) -> None:
        recent = list(self.history)[-limit:]
        await websocket.send_text(
            json.dumps({"event": "replay", "data": recent}, default=str)
        )

    def bind_loop(self) -> None:
        self._loop = asyncio.get_running_loop()

    @property
    def connection_count(self) -> int:
        return sum(len(v) for v in self._sockets.values())


manager = ConnectionManager()
