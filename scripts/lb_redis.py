"""Redis live registry (aligned with Java LoadNodeRegistryKeys)."""

from __future__ import annotations

import os
import time
from typing import Dict, Optional

try:
    import redis
except ImportError:
    redis = None  # type: ignore

NODE_PREFIX = "lb:live:"


def _client():
    if redis is None:
        return None
    host = os.environ.get("REDIS_HOST", "redis")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    return redis.Redis(host=host, port=port, db=0, decode_responses=True, socket_timeout=0.2)


def read_live_state(node_id: str, ttl_ms: int = 10_000) -> Optional[Dict[str, float | int | bool]]:
    r = _client()
    if r is None:
        return None
    key = NODE_PREFIX + node_id
    try:
        data = r.hgetall(key)
    except Exception:
        return None
    if not data:
        return None
    updated = int(data.get("updatedAt", "0") or 0)
    if updated <= 0 or (time.time() * 1000 - updated) > ttl_ms:
        return None
    return {
        "active": int(data.get("active", "0") or 0),
        "ewma": int(data.get("ewmaRtMs", "0") or 0),
        "online": data.get("online", "0") == "1",
    }


def merge_into_states(states: dict, server_ids: list[str], ttl_ms: int = 10_000) -> None:
    for sid in server_ids:
        live = read_live_state(sid, ttl_ms)
        if live is None or sid not in states:
            continue
        st = states[sid]
        st.active_requests = int(live["active"])
        st.ewma_response_time_ms = int(live["ewma"])
        st.online = st.online and bool(live["online"])
