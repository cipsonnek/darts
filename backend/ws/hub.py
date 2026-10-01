"""WebSocket fan-out. Producers in any thread call :meth:`EventHub.publish`; each connected
client has a bounded queue (the oldest messages are dropped for a slow client, so one bad
connection can never stall the engine or other clients)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("backend.ws")

_QUEUE_SIZE = 256


@dataclass(eq=False)
class Client:
    ws: WebSocket
    channels: set[str]
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=_QUEUE_SIZE))
    dropped: int = 0


class EventHub:
    def __init__(self) -> None:
        self._clients: set[Client] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._seq = 0
        self.published = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def publish(self, channel: str, type_: str, data: Any) -> None:
        """Thread-safe."""
        self._seq += 1
        msg = {"seq": self._seq, "channel": channel, "type": type_, "ts": time.time(), "data": data}
        self.published += 1
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._fanout(msg)
        else:
            loop.call_soon_threadsafe(self._fanout, msg)

    def _fanout(self, msg: dict) -> None:
        payload = json.dumps(msg, default=_default)
        for c in list(self._clients):
            if msg["channel"] not in c.channels and "*" not in c.channels:
                continue
            if c.queue.full():
                try:
                    c.queue.get_nowait()
                    c.dropped += 1
                except asyncio.QueueEmpty:
                    pass
            c.queue.put_nowait(payload)

    async def serve(self, ws: WebSocket, channels: set[str], hello: dict | None = None) -> None:
        await ws.accept()
        client = Client(ws, channels)
        self._clients.add(client)
        log.info("websocket connected", extra={"channels": sorted(channels), "clients": len(self._clients)})
        if hello is not None:
            await ws.send_text(json.dumps({"seq": 0, "channel": "system", "type": "hello", "ts": time.time(),
                                           "data": hello}, default=_default))
        sender = asyncio.create_task(self._sender(client))
        try:
            while True:
                text = await ws.receive_text()
                await self._handle_client_message(client, text)
        except Exception:  # noqa: BLE001 - disconnects arrive as exceptions
            pass
        finally:
            sender.cancel()
            self._clients.discard(client)
            log.info("websocket disconnected", extra={"clients": len(self._clients), "dropped": client.dropped})

    async def _sender(self, client: Client) -> None:
        try:
            while True:
                payload = await client.queue.get()
                await client.ws.send_text(payload)
        except Exception:  # noqa: BLE001
            return

    async def _handle_client_message(self, client: Client, text: str) -> None:
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(msg, dict):
            return
        if msg.get("type") == "subscribe" and isinstance(msg.get("channels"), list):
            client.channels = {str(c)[:32] for c in msg["channels"][:16]}
        elif msg.get("type") == "ping":
            await client.ws.send_text(json.dumps({"type": "pong", "ts": time.time()}))


def _default(o: Any) -> Any:
    try:
        import numpy as np

        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer, np.bool_)):
            return o.item()
    except ImportError:  # pragma: no cover
        pass
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)
