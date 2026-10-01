"""TCP probe helpers."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass


@dataclass(slots=True)
class TCPProbeResult:
    """Result of a single TCP probe."""

    availability: int
    latency_ms: float
    error: str | None = None


async def probe_tcp(host: str, port: int, timeout_seconds: float = 3) -> TCPProbeResult:
    """Open a TCP connection and measure how long it takes."""

    start_time = time.perf_counter()

    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout_seconds)
        latency_ms = (time.perf_counter() - start_time) * 1000

        writer.close()
        with suppress(Exception):
            await writer.wait_closed()

        return TCPProbeResult(
            availability=1,
            latency_ms=round(latency_ms, 2),
            error=None,
        )
    except Exception as exc:
        return TCPProbeResult(
            availability=0,
            latency_ms=0.0,
            error=str(exc),
        )
