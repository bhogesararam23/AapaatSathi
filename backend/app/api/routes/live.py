"""WebSocket live feed."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.deps import user_from_token
from app.core.events import OPS, PUBLIC, manager
from app.db import SessionLocal

log = logging.getLogger("aapaatsathi.api.live")

router = APIRouter(tags=["live"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, channel: str = "public", token: str = "") -> None:
    """``/ws?channel=public`` for the citizen map, ``channel=ops`` for staff.

    The ops channel carries reporter-linked activity, so it requires a valid
    staff token; the public channel carries only anonymised scores.
    """
    manager.bind_loop()
    requested = OPS if channel == "ops" else PUBLIC
    if requested == OPS:
        async with SessionLocal() as session:
            try:
                user = await user_from_token(token or None, session)
            except Exception:
                user = None
        if not user or user.role == "citizen":
            await websocket.close(code=4403)
            return

    await manager.connect(websocket, requested)
    try:
        await manager.send_history(websocket, limit=30)
        while True:
            # Client frames are heartbeats/acks; we keep reading so the server
            # notices disconnects promptly instead of leaking sockets.
            text = await websocket.receive_text()
            if text.strip().lower() in {"ping", "hb"}:
                await websocket.send_text('{"event":"pong","data":null}')
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - transport layer noise
        log.debug("websocket closed: %s", exc)
    finally:
        await manager.disconnect(websocket, requested)
