"""HTTP and HTTPS probe helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass

import aiohttp


@dataclass(slots=True)
class HTTPProbeResult:
    """Result of a single HTTP probe."""

    availability: int
    response_time_ms: float
    status_code: int
    error: str | None = None


async def probe_http(
    url: str,
    session: aiohttp.ClientSession,
    timeout_seconds: float = 5,
) -> HTTPProbeResult:
    """Send an HTTP GET request and measure response time.

    The target is considered UP when it returns a status code in the 2xx or 3xx range.
    """

    start_time = time.perf_counter()

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with session.get(url, timeout=timeout, allow_redirects=True) as response:
            await response.read()
            response_time_ms = (time.perf_counter() - start_time) * 1000
            availability = 1 if 200 <= response.status < 400 else 0

            return HTTPProbeResult(
                availability=availability,
                response_time_ms=round(response_time_ms, 2),
                status_code=response.status,
                error=None if availability == 1 else f"Received HTTP status {response.status}",
            )
    except Exception as exc:
        return HTTPProbeResult(
            availability=0,
            response_time_ms=0.0,
            status_code=0,
            error=str(exc),
        )
