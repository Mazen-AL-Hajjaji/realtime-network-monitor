"""Load monitoring targets from YAML configuration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MonitorTarget:
    """One monitoring target loaded from config/targets.yaml."""

    name: str
    url: str
    host: str
    port: int | None
    enabled: bool = True


def get_default_config_path() -> Path:
    """Return the default targets.yaml path inside the project."""

    return Path(__file__).resolve().parents[1] / "config" / "targets.yaml"


def _normalize_port(raw_value: Any, target_name: str) -> int | None:
    """Convert the YAML port value into an integer when possible."""

    if raw_value in (None, ""):
        return None

    try:
        return int(raw_value)
    except (TypeError, ValueError):
        logger.warning("Skipping target %s because port is invalid: %r", target_name, raw_value)
        return None


def _build_target(item: dict[str, Any]) -> MonitorTarget | None:
    """Validate a raw YAML object and convert it into a MonitorTarget."""

    name = str(item.get("name", "")).strip()
    if not name:
        logger.warning("Skipping one target because it has no name.")
        return None

    url = str(item.get("url", "")).strip()
    host = str(item.get("host", "")).strip()
    port = _normalize_port(item.get("port"), name)
    enabled = bool(item.get("enabled", True))

    return MonitorTarget(
        name=name,
        url=url,
        host=host,
        port=port,
        enabled=enabled,
    )


def load_targets(config_path: str | Path | None = None) -> list[MonitorTarget]:
    """Load targets from YAML.

    Expected format:
    targets:
      - name: Example
        url: https://example.com
        host: example.com
        port: 443
        enabled: true
    """

    resolved_path = Path(config_path) if config_path else get_default_config_path()

    if not resolved_path.exists():
        logger.warning("Targets file not found: %s", resolved_path)
        return []

    try:
        with resolved_path.open("r", encoding="utf-8") as file:
            raw_data = yaml.safe_load(file) or {}
    except yaml.YAMLError:
        logger.exception("Failed to parse YAML file: %s", resolved_path)
        return []
    except OSError:
        logger.exception("Failed to read targets file: %s", resolved_path)
        return []

    raw_targets = raw_data.get("targets", [])
    if not isinstance(raw_targets, list):
        logger.warning("Expected 'targets' to be a list in %s", resolved_path)
        return []

    targets: list[MonitorTarget] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            logger.warning("Skipping a target because it is not a YAML object: %r", item)
            continue

        target = _build_target(item)
        if target:
            targets.append(target)

    return targets
