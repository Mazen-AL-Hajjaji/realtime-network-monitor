"""FastAPI entry point for the real-time network monitor."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import aiohttp
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.config_loader import get_default_config_path, load_targets
from app.metrics import sync_target_metrics, update_http_metrics, update_last_probe_timestamp, update_tcp_metrics
from app.probes.http_probe import probe_http
from app.probes.tcp_probe import probe_tcp

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

APP_NAME = "Real-Time Network Health & Latency Monitoring Dashboard"
DEFAULT_CONFIG_PATH = get_default_config_path()
CONFIG_PATH = Path(os.getenv("TARGETS_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
PROBE_INTERVAL_SECONDS = float(os.getenv("PROBE_INTERVAL_SECONDS", "5"))
TCP_TIMEOUT_SECONDS = float(os.getenv("TCP_TIMEOUT_SECONDS", "3"))
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "5"))


class MonitorService:
    """Background service that runs TCP and HTTP probes on a fixed interval."""

    def __init__(self, config_path: Path, interval_seconds: float) -> None:
        self.config_path = config_path
        self.interval_seconds = interval_seconds
        self.session: aiohttp.ClientSession | None = None
        self.task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self.task is not None and not self.task.done()

    async def start(self) -> None:
        """Create the shared HTTP session and start the monitoring loop."""

        if self.is_running:
            return

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": "realtime-network-monitor/1.0"},
        )
        self.task = asyncio.create_task(self._run_loop(), name="network-monitor-loop")
        logger.info("Monitoring service started with interval=%ss", self.interval_seconds)

    async def stop(self) -> None:
        """Stop the monitoring loop and close the HTTP session."""

        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None

        if self.session:
            await self.session.close()
            self.session = None

        logger.info("Monitoring service stopped.")

    async def _run_loop(self) -> None:
        """Repeatedly load the YAML config and probe all enabled targets."""

        while True:
            try:
                targets = load_targets(self.config_path)
                enabled_targets = [target for target in targets if target.enabled]

                sync_target_metrics(targets)

                if enabled_targets:
                    await asyncio.gather(*(self._probe_target(target) for target in enabled_targets))
                else:
                    logger.warning("No enabled targets found in %s", self.config_path)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in monitoring loop.")

            await asyncio.sleep(self.interval_seconds)

    async def _probe_target(self, target) -> None:
        """Probe one target using both TCP and HTTP checks when configured."""

        probe_tasks: list[asyncio.Future] = []

        if target.host and target.port is not None:
            probe_tasks.append(asyncio.create_task(self._run_tcp_probe(target)))

        if target.url:
            probe_tasks.append(asyncio.create_task(self._run_http_probe(target)))

        if not probe_tasks:
            logger.warning("Target %s has no usable probe settings.", target.name)
            return

        await asyncio.gather(*probe_tasks)
        update_last_probe_timestamp(target.name, time.time())

    async def _run_tcp_probe(self, target) -> None:
        """Run the TCP probe and push results into Prometheus metrics."""

        result = await probe_tcp(target.host, target.port, timeout_seconds=TCP_TIMEOUT_SECONDS)
        update_tcp_metrics(target.name, target.host, target.port, result.availability, result.latency_ms)

        if result.availability == 0:
            logger.warning("TCP probe failed for %s (%s:%s): %s", target.name, target.host, target.port, result.error)

    async def _run_http_probe(self, target) -> None:
        """Run the HTTP probe and push results into Prometheus metrics."""

        if self.session is None:
            logger.warning("HTTP client session is not ready yet.")
            return

        result = await probe_http(target.url, self.session, timeout_seconds=HTTP_TIMEOUT_SECONDS)
        update_http_metrics(
            target.name,
            target.url,
            result.availability,
            result.response_time_ms,
            result.status_code,
        )

        if result.availability == 0:
            logger.warning("HTTP probe failed for %s (%s): %s", target.name, target.url, result.error)


monitor_service = MonitorService(CONFIG_PATH, PROBE_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """FastAPI startup and shutdown hooks."""

    await monitor_service.start()
    try:
        yield
    finally:
        await monitor_service.stop()


app = FastAPI(
    title=APP_NAME,
    version=__version__,
    lifespan=lifespan,
)


@app.get("/")
async def home() -> dict[str, object]:
    """Simple home endpoint with project information."""

    return {
        "project": APP_NAME,
        "version": __version__,
        "description": "A FastAPI-based monitoring agent that exposes Prometheus metrics for TCP and HTTP checks.",
        "endpoints": {
            "home": "/",
            "health": "/health",
            "metrics": "/metrics",
        },
        "config_path": str(CONFIG_PATH),
        "probe_interval_seconds": PROBE_INTERVAL_SECONDS,
    }


@app.get("/health")
async def health() -> dict[str, object]:
    """Basic application health endpoint."""

    return {
        "status": "ok",
        "monitoring_loop_running": monitor_service.is_running,
        "timestamp": time.time(),
    }


@app.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics."""

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
