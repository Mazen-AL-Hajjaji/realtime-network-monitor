"""Prometheus metric definitions and update helpers."""

from __future__ import annotations

from typing import Iterable

from prometheus_client import Gauge

from app.config_loader import MonitorTarget

NETWORK_TCP_UP = Gauge(
    "network_tcp_up",
    "TCP availability status. 1 means UP, 0 means DOWN.",
    ["target_name", "host", "port"],
)

NETWORK_TCP_LATENCY_MS = Gauge(
    "network_tcp_latency_ms",
    "TCP connection latency in milliseconds.",
    ["target_name", "host", "port"],
)

NETWORK_HTTP_UP = Gauge(
    "network_http_up",
    "HTTP availability status. 1 means UP, 0 means DOWN.",
    ["target_name", "url"],
)

NETWORK_HTTP_RESPONSE_TIME_MS = Gauge(
    "network_http_response_time_ms",
    "HTTP response time in milliseconds.",
    ["target_name", "url"],
)

NETWORK_HTTP_STATUS_CODE = Gauge(
    "network_http_status_code",
    "Last HTTP status code seen for the target.",
    ["target_name", "url"],
)

MONITORING_AGENT_LAST_PROBE_TIMESTAMP = Gauge(
    "monitoring_agent_last_probe_timestamp",
    "Unix timestamp of the last completed probe for a target.",
    ["target_name"],
)

_active_tcp_labels: set[tuple[str, str, str]] = set()
_active_http_labels: set[tuple[str, str]] = set()
_active_timestamp_labels: set[tuple[str]] = set()


def _safe_remove(metric: Gauge, labels: tuple[str, ...]) -> None:
    """Remove a label set if it exists."""

    try:
        metric.remove(*labels)
    except KeyError:
        pass


def sync_target_metrics(targets: Iterable[MonitorTarget]) -> None:
    """Remove metric series for targets that were deleted or disabled.

    This keeps Prometheus output aligned with the current YAML file.
    """

    global _active_tcp_labels, _active_http_labels, _active_timestamp_labels

    new_tcp_labels: set[tuple[str, str, str]] = set()
    new_http_labels: set[tuple[str, str]] = set()
    new_timestamp_labels: set[tuple[str]] = set()

    for target in targets:
        if not target.enabled:
            continue

        new_timestamp_labels.add((target.name,))

        if target.host and target.port is not None:
            new_tcp_labels.add((target.name, target.host, str(target.port)))

        if target.url:
            new_http_labels.add((target.name, target.url))

    for labels in _active_tcp_labels - new_tcp_labels:
        _safe_remove(NETWORK_TCP_UP, labels)
        _safe_remove(NETWORK_TCP_LATENCY_MS, labels)

    for labels in _active_http_labels - new_http_labels:
        _safe_remove(NETWORK_HTTP_UP, labels)
        _safe_remove(NETWORK_HTTP_RESPONSE_TIME_MS, labels)
        _safe_remove(NETWORK_HTTP_STATUS_CODE, labels)

    for labels in _active_timestamp_labels - new_timestamp_labels:
        _safe_remove(MONITORING_AGENT_LAST_PROBE_TIMESTAMP, labels)

    _active_tcp_labels = new_tcp_labels
    _active_http_labels = new_http_labels
    _active_timestamp_labels = new_timestamp_labels


def update_tcp_metrics(target_name: str, host: str, port: int, availability: int, latency_ms: float) -> None:
    """Store the latest TCP probe result."""

    labels = {"target_name": target_name, "host": host, "port": str(port)}
    NETWORK_TCP_UP.labels(**labels).set(availability)
    NETWORK_TCP_LATENCY_MS.labels(**labels).set(latency_ms)


def update_http_metrics(
    target_name: str,
    url: str,
    availability: int,
    response_time_ms: float,
    status_code: int,
) -> None:
    """Store the latest HTTP probe result."""

    labels = {"target_name": target_name, "url": url}
    NETWORK_HTTP_UP.labels(**labels).set(availability)
    NETWORK_HTTP_RESPONSE_TIME_MS.labels(**labels).set(response_time_ms)
    NETWORK_HTTP_STATUS_CODE.labels(**labels).set(status_code)


def update_last_probe_timestamp(target_name: str, timestamp: float) -> None:
    """Store the Unix timestamp of the latest completed probe."""

    MONITORING_AGENT_LAST_PROBE_TIMESTAMP.labels(target_name=target_name).set(timestamp)
