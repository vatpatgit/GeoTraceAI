"""Provider status for the UI (truthful, cached 60 s) and selection helpers."""
from __future__ import annotations

import time
from typing import Any

from app.providers.sentinel import get_provider

_status_cache: dict[str, Any] = {"at": 0.0, "value": None, "key": None}


async def provider_status(force: bool = False) -> list[dict[str, Any]]:
    provider = get_provider()
    if provider is None:
        return [{"provider": "none", "configured": False, "catalog": "not_configured", "imagery": "not_configured",
                 "detail": "Sentinel integration disabled (SENTINEL_PROVIDER=none)."}]
    key = id(provider)
    if not force and _status_cache["value"] is not None and _status_cache["key"] == key and time.time() - _status_cache["at"] < 60:
        return _status_cache["value"]
    probe = await provider.probe()
    configured = probe.get("imagery") != "not_configured"
    value = [{"provider": provider.name, "configured": configured, "catalog": probe["catalog"], "imagery": probe["imagery"],
              "detail": probe.get("detail", "")}]
    _status_cache.update(at=time.time(), value=value, key=key)
    return value


def reset_status_cache() -> None:
    _status_cache.update(at=0.0, value=None, key=None)
