"""
HTTP service + file writer for precomputed per-bin routing decisions.

Polls nodes, merges Redis live in-flight state, applies hysteresis on winner changes,
writes full + compact atlas (with route-owned compute units for OpenResty).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from custom_load_balancer import CustomLoadBalancer, load_config

HYSTERESIS_MARGIN = 0.05
FAST_REFRESH_SEC = 0.5
FAST_REFRESH_DURATION_SEC = 30.0


def _normalize_upstream(url: str) -> str:
    u = url.strip()
    if not u:
        return "http://127.0.0.1:8080"
    if u.startswith("http://") or u.startswith("https://"):
        return u.rstrip("/")
    return "http://" + u.lstrip("/")


def _top_candidates(
    ranked: list,
    edge_choices: int,
    previous_id: Optional[str],
) -> List[Dict[str, str]]:
    online = [(s, m) for s, m in ranked if s.online]
    if not online:
        if ranked:
            s = ranked[0][0]
            return [{"id": s.id, "upstream": _normalize_upstream(s.base_url)}]
        return []

    best_state, best_metrics = online[0]
    best_score = best_metrics["rank_score"]
    ordered: List[Tuple[Any, Dict[str, float]]] = []

    if previous_id:
        for state, metrics in online:
            if state.id == previous_id:
                keep = state.id == best_state.id or best_score <= 0 or metrics["rank_score"] >= best_score * (
                    1.0 - HYSTERESIS_MARGIN
                )
                if keep:
                    ordered.append((state, metrics))
                break

    for state, metrics in online:
        if any(s.id == state.id for s, _ in ordered):
            continue
        ordered.append((state, metrics))
        if len(ordered) >= edge_choices:
            break

    return [{"id": s.id, "upstream": _normalize_upstream(s.base_url)} for s, _ in ordered]


def build_cache_payload(
    lb: CustomLoadBalancer,
    edge_choices: int = 2,
    previous_winners: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    lb.refresh()
    edge_choices = max(1, edge_choices)
    prev = previous_winners or {}
    bins = lb._build_log_bins()
    fallback_candidates: List[Dict[str, str]] = []
    bin_entries: List[Dict[str, Any]] = []
    new_winners: Dict[str, str] = {}

    for b in bins:
        ranked = lb._rank_for_bin(b.center, b.center)
        candidates = _top_candidates(ranked, edge_choices, prev.get(b.label))
        winner_id = candidates[0]["id"] if candidates else None
        new_winners[b.label] = winner_id or ""
        primary = candidates[0]["upstream"] if candidates else "http://127.0.0.1:8080"
        if not fallback_candidates and candidates:
            fallback_candidates = list(candidates)
        bin_entries.append(
            {
                "label": b.label,
                "minInclusive": b.min_inclusive,
                "maxExclusive": b.max_exclusive,
                "center": b.center,
                "selectedServerId": winner_id,
                "upstream": primary,
                "upstreams": [c["upstream"] for c in candidates],
                "candidates": candidates,
            }
        )

    if not fallback_candidates:
        fallback_candidates = [{"id": "fallback", "upstream": "http://127.0.0.1:8080"}]

    return {
        "version": int(time.time()),
        "edgeChoices": edge_choices,
        "bins": bin_entries,
        "fallback": fallback_candidates[0]["upstream"],
        "fallbackUpstreams": [c["upstream"] for c in fallback_candidates],
        "fallbackCandidates": fallback_candidates,
        "_winners": new_winners,
    }


def build_compact_payload(
    full: Dict[str, Any],
    route_compute: Dict[str, int],
    max_compute_units: int,
    default_compute_units: int,
) -> Dict[str, Any]:
    fallback_candidates = full.get("fallbackCandidates") or [
        {"id": "fallback", "upstream": full.get("fallback", "http://127.0.0.1:8080")}
    ]
    routes = []
    for b in full.get("bins", []):
        candidates = b.get("candidates")
        if not candidates:
            upstreams = b.get("upstreams") or [b.get("upstream", "http://127.0.0.1:8080")]
            candidates = [{"id": b.get("selectedServerId", "?"), "upstream": u} for u in upstreams]
        routes.append(
            {
                "minInclusive": b["minInclusive"],
                "maxExclusive": b["maxExclusive"],
                "candidates": candidates,
            }
        )
    return {
        "edgeChoices": full.get("edgeChoices", 2),
        "fallbackCandidates": fallback_candidates,
        "routes": routes,
        "routeCompute": route_compute,
        "maxComputeUnits": max_compute_units,
        "defaultComputeUnits": default_compute_units,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "DecisionCache/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/health/"):
            self._send(200, b'{"status":"UP"}\n')
            return
        if path in ("/cache.json", "/cache.json/"):
            app: DecisionCacheApp = self.server.app  # type: ignore[attr-defined]
            payload = app.latest_payload()
            body = json.dumps(payload, indent=2 if "pretty" in self.path else None, ensure_ascii=False).encode(
                "utf-8"
            )
            self._send(200, body + b"\n")
            return
        self._send(404, b'{"error":"not found"}\n')

    def _send(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class DecisionCacheApp:
    def __init__(
        self,
        lb: CustomLoadBalancer,
        cache_file: str | None,
        compact_cache_file: str | None,
        refresh_interval_sec: float,
        edge_choices: int,
        route_compute: Dict[str, int],
        max_compute_units: int,
        default_compute_units: int,
    ) -> None:
        self.lb = lb
        self.cache_file = cache_file
        self.compact_cache_file = compact_cache_file
        self.refresh_interval_sec = max(0.25, refresh_interval_sec)
        self.edge_choices = max(1, edge_choices)
        self.route_compute = route_compute
        self.max_compute_units = max_compute_units
        self.default_compute_units = default_compute_units
        self._lock = threading.Lock()
        self._payload: Dict[str, Any] = {}
        self._previous_winners: Dict[str, str] = {}
        self._fast_refresh_until = 0.0

    def latest_payload(self) -> Dict[str, Any]:
        with self._lock:
            if self._payload:
                return {k: v for k, v in self._payload.items() if k != "_winners"}
            return build_cache_payload(self.lb, self.edge_choices)

    def _current_interval(self) -> float:
        if time.time() < self._fast_refresh_until:
            return FAST_REFRESH_SEC
        return self.refresh_interval_sec

    def refresh_loop(self) -> None:
        while True:
            interval = self._current_interval()
            try:
                payload = build_cache_payload(self.lb, self.edge_choices, self._previous_winners)
                winners = payload.pop("_winners", {})
                self._previous_winners = winners
                with self._lock:
                    self._payload = payload
                if self.cache_file:
                    with open(self.cache_file, "w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                if self.compact_cache_file:
                    compact = build_compact_payload(
                        payload, self.route_compute, self.max_compute_units, self.default_compute_units
                    )
                    with open(self.compact_cache_file, "w", encoding="utf-8") as f:
                        json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))
            except Exception as ex:
                print(f"[decision-cache] refresh failed: {ex}", flush=True)
                self._fast_refresh_until = time.time() + FAST_REFRESH_DURATION_SEC
            time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--cache-file")
    parser.add_argument("--compact-cache-file")
    parser.add_argument("--edge-choices", type=int, default=2)
    args = parser.parse_args()

    servers, weights, route_compute, max_compute, default_compute = load_config(args.config)
    lb = CustomLoadBalancer(
        servers=servers,
        overhead_weight=float(weights.get("overheadWeight", 0.40)),
        price_weight=float(weights.get("priceWeight", 1.20)),
        underpowered_penalty=float(weights.get("underpoweredPenalty", 0.35)),
        sla_fit_threshold=float(weights.get("slaFitThreshold", 1.0)),
        log_min_load=int(weights.get("logMinLoad", 1)),
        log_max_load=int(weights.get("logMaxLoad", 2048)),
        log_base=int(weights.get("logBase", 2)),
        load_weight=float(weights.get("loadWeight", 25.0)),
        concurrency_capacity_factor=float(weights.get("concurrencyCapacityFactor", 1.0)),
    )

    app = DecisionCacheApp(
        lb,
        args.cache_file,
        args.compact_cache_file,
        args.interval,
        args.edge_choices,
        route_compute,
        max_compute,
        default_compute,
    )
    app._payload = build_cache_payload(lb, app.edge_choices)  # noqa: SLF001
    app._payload.pop("_winners", None)
    if args.cache_file:
        with open(args.cache_file, "w", encoding="utf-8") as f:
            json.dump(app._payload, f, ensure_ascii=False, indent=2)  # noqa: SLF001
    if args.compact_cache_file:
        with open(args.compact_cache_file, "w", encoding="utf-8") as f:
            json.dump(
                build_compact_payload(app._payload, route_compute, max_compute, default_compute),
                f,
                ensure_ascii=False,
                separators=(",", ":"),
            )

    threading.Thread(target=app.refresh_loop, daemon=True).start()
    httpd = HTTPServer((args.host, args.port), Handler)
    httpd.app = app  # type: ignore[attr-defined]
    print(f"[decision-cache] listening on http://{args.host}:{args.port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
