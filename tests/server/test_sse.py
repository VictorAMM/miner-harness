"""Testes do SseChannel."""

from __future__ import annotations

import asyncio
import json

import pytest

from miner_harness.server.sse import SseChannel


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestSseChannel:
    def test_send_formats_sse_message(self) -> None:
        ch = SseChannel()
        ch.send("step_start", {"step": "tectonic_history"})
        ch.close()

        chunks: list[str] = []

        async def collect() -> None:
            async for chunk in ch:
                chunks.append(chunk)

        _run(collect())

        assert len(chunks) == 1
        msg = chunks[0]
        assert "event: step_start\n" in msg
        assert "data: " in msg
        data_line = [l for l in msg.split("\n") if l.startswith("data: ")][0]
        payload = json.loads(data_line[len("data: "):])
        assert payload["step"] == "tectonic_history"

    def test_close_stops_iteration(self) -> None:
        ch = SseChannel()
        ch.send("ping", {})
        ch.close()

        collected: list[str] = []

        async def collect() -> None:
            async for chunk in ch:
                collected.append(chunk)

        _run(collect())
        assert len(collected) == 1

    def test_counter_increments(self) -> None:
        ch = SseChannel()
        ch.send("a", {})
        ch.send("b", {})
        ch.close()

        chunks: list[str] = []

        async def collect() -> None:
            async for chunk in ch:
                chunks.append(chunk)

        _run(collect())

        ids = [int(l.split(": ")[1]) for chunk in chunks for l in chunk.split("\n") if l.startswith("id: ")]
        assert ids == [1, 2]

    def test_multiple_sends_before_iterate(self) -> None:
        ch = SseChannel()
        for i in range(3):
            ch.send("ev", {"i": i})
        ch.close()

        chunks: list[str] = []

        async def collect() -> None:
            async for chunk in ch:
                chunks.append(chunk)

        _run(collect())
        assert len(chunks) == 3

    def test_empty_channel_closes_immediately(self) -> None:
        ch = SseChannel()
        ch.close()

        chunks: list[str] = []

        async def collect() -> None:
            async for chunk in ch:
                chunks.append(chunk)

        _run(collect())
        assert chunks == []

    @pytest.mark.asyncio
    async def test_aiter_protocol(self) -> None:
        ch = SseChannel()
        ch.send("test", {"x": 1})
        ch.close()

        chunks: list[str] = []
        async for chunk in ch:
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "event: test" in chunks[0]
