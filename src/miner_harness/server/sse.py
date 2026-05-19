"""SseChannel — fila assíncrona para streaming de Server-Sent Events."""

from __future__ import annotations

import asyncio
import json


class SseChannel:
    """Canal SSE baseado em asyncio.Queue.

    Uso:
        channel = SseChannel()
        channel.send("step_start", {"step": "tectonic_history"})
        channel.close()

        async for chunk in channel:
            await response.write(chunk.encode())
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._counter = 0

    def send(self, event: str, data: dict) -> None:
        """Enfileira uma mensagem SSE formatada."""
        self._counter += 1
        payload = (
            f"id: {self._counter}\n"
            f"event: {event}\n"
            f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        )
        self._queue.put_nowait(payload)

    def close(self) -> None:
        """Sinaliza fim do stream."""
        self._queue.put_nowait(None)

    def __aiter__(self) -> SseChannel:
        return self

    async def __anext__(self) -> str:
        msg = await self._queue.get()
        if msg is None:
            raise StopAsyncIteration
        return msg
