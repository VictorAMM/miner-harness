"""SSE channel throughput benchmarks."""

from __future__ import annotations

import time

import pytest

from miner_harness.server.sse import SseChannel


class TestSseThroughput:
    @pytest.mark.asyncio
    async def test_1000_events_under_500ms(self) -> None:
        """Sending and consuming 1000 SSE events should complete in under 500 ms."""
        channel = SseChannel()

        t0 = time.perf_counter()
        for i in range(1000):
            channel.send("step_complete", {"step": f"step_{i}", "index": i})
        channel.close()

        count = 0
        async for _ in channel:
            count += 1
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert count == 1000
        assert elapsed_ms < 500, f"SSE 1000 events too slow: {elapsed_ms:.1f}ms"

    @pytest.mark.asyncio
    async def test_event_counter_increments_monotonically(self) -> None:
        """Event IDs must increment by 1 for each send call."""
        channel = SseChannel()
        for i in range(5):
            channel.send("ping", {"i": i})
        channel.close()

        ids: list[int] = []
        async for chunk in channel:
            for line in chunk.split("\n"):
                if line.startswith("id: "):
                    ids.append(int(line[4:]))

        assert ids == list(range(1, 6))

    @pytest.mark.asyncio
    async def test_large_payload_under_100ms(self) -> None:
        """A single event with a 10 KB payload should enqueue in under 100 ms."""
        channel = SseChannel()
        big_payload = {"data": "x" * 10_000}

        t0 = time.perf_counter()
        channel.send("big", big_payload)
        channel.close()
        async for _ in channel:
            pass
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 100, f"Large payload too slow: {elapsed_ms:.1f}ms"

    @pytest.mark.asyncio
    async def test_closed_channel_yields_no_events(self) -> None:
        """A channel closed before any sends yields zero chunks."""
        channel = SseChannel()
        channel.close()
        chunks = [c async for c in channel]
        assert chunks == []
