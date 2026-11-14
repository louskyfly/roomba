"""Hub WebSocket : diffusion des événements vers l'interface."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    def broadcast(self, payload: dict[str, Any]) -> None:
        """Diffusion non bloquante : peut être appelée depuis un callback."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._send_all(json.dumps(payload, ensure_ascii=False)))

    async def _send_all(self, message: str) -> None:
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                await self.disconnect(ws)


hub = Hub()
