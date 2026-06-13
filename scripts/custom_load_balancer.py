"""
Custom load distribution script.

What it does:
1) Polls each server /internal/node-info endpoint.
2) Tracks online/offline state (not busy state).
3) Emits notification only when a server changes from offline -> online.
4) Chooses the best server for a request based on expected compute units.

Usage:
  python scripts/custom_load_balancer.py --config scripts/servers.json --watch
  python scripts/custom_load_balancer.py --config scripts/servers.json --route 450
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from typing import Dict, List
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


@dataclass
class ServerConfig:
    id: str
    base_url: str
    info_path: str = "/internal/node-info"
    weight: float = 1.0
    capability_override: float | None = None


@dataclass
class ServerState:
    id: str
    base_url: str
    online: bool
    cpu_cores: float
    cpu_clock_ghz: float
    ram_gb: float
    overhead_ms: float
    request_price: float
    active_requests: int = 0
    in_flight_compute_units: int = 0
    ewma_response_time_ms: int = 0
    weight: float = 1.0


@dataclass
class LoadBin:
    label: str
    min_inclusive: float
    max_exclusive: float
    center: float

    def contains(self, expected_compute_units: float) -> bool:
        return self.min_inclusive <= expected_compute_units < self.max_exclusive


class CustomLoadBalancer:
    def __init__(
        self,
        servers: List[ServerConfig],
        overhead_weight: float = 0.40,
        price_weight: float = 1.20,
        underpowered_penalty: float = 0.35,
        sla_fit_threshold: float = 1.0,
        log_min_load: int = 1,
        log_max_load: int = 2048,
        log_base: int = 2,
        load_weight: float = 25.0,
        concurrency_capacity_factor: float = 1.0,
        max_active_requests: int = 64,
        target_response_time_ms: int = 200,
    ) -> None:
        self.servers = servers
        self.overhead_weight = overhead_weight
        self.price_weight = price_weight
        self.underpowered_penalty = underpowered_penalty
        self.sla_fit_threshold = sla_fit_threshold
        self.load_weight = load_weight
        self.concurrency_capacity_factor = max(0.01, float(concurrency_capacity_factor))
        self.max_active_requests = max(1, int(max_active_requests))
        self.target_response_time_ms = max(1, int(target_response_time_ms))
        self.log_min_load = max(1, int(log_min_load))
        self.log_max_load = max(self.log_min_load + 1, int(log_max_load))
        self.log_base = max(2, int(log_base))
        self.states: Dict[str, ServerState] = {}
        self.was_online: Dict[str, bool] = {}

    def refresh(self) -> None:
        for server in self.servers:
            previous_online = self.was_online.get(server.id, False)
            current = self._fetch(server)
            self.states[server.id] = current
            self.was_online[server.id] = current.online
        try:
            from lb_redis import merge_into_states

            merge_into_states(self.states, [s.id for s in self.servers])
        except Exception:
            pass
            if not previous_online and current.online:
                self._notify_back_online(current)

    def route(self, expected_compute_units: float) -> ServerState:
        if expected_compute_units <= 0:
            raise ValueError("expected_compute_units must be > 0")

        bins = self._build_log_bins()
        selected_bin = self._find_bin(bins, expected_compute_units)
        ranked_for_bin = self._rank_for_bin(selected_bin.center, expected_compute_units)

        if not any(state.online for state in self.states.values()):
            raise RuntimeError("No online server available for routing")

        for state, _ in ranked_for_bin:
            if state.online:
                return state
        raise RuntimeError("No online server available for routing")

    def table(self) -> Dict[str, List[Dict[str, float | str]]]:
        routing_table: Dict[str, List[Dict[str, float | str]]] = {}
        for b in self._build_log_bins():
            ranked = self._rank_for_bin(b.center, b.center)
            routing_table[b.label] = [
                {
                    "serverId": state.id,
                    "pSla": round(metrics["p_sla"], 6),
                    "cost": round(metrics["cost"], 6),
                    "fitRatio": round(metrics["fit_ratio"], 6),
                    "staticRankScore": round(metrics["static_rank_score"], 6),
                    "activeRequests": metrics["active_requests"],
                    "inFlightComputeUnits": metrics["in_flight_compute_units"],
                    "maxInFlightComputeUnits": metrics["max_in_flight"],
                    "weight": round(metrics["weight"], 4),
                    "loadPressure": round(metrics["load_pressure"], 6),
                    "rankScore": round(metrics["rank_score"], 6),
                }
                for state, metrics in ranked
            ]
        return routing_table

    def _fetch(self, server: ServerConfig) -> ServerState:
        url = server.base_url.rstrip("/") + "/" + server.info_path.lstrip("/")
        req = Request(url, method="GET")
        try:
            with urlopen(req, timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            weight = server.weight if server.weight > 0 else 1.0
            return ServerState(
                id=server.id,
                base_url=server.base_url,
                online=bool(payload.get("availableForRequests", False)),
                cpu_cores=float(payload.get("cpuCores", 0)),
                cpu_clock_ghz=float(payload.get("cpuClockGhz", 0)),
                ram_gb=float(payload.get("ramGb", 0)),
                overhead_ms=float(payload.get("overheadMs", 0)),
                request_price=float(payload.get("requestPrice", 0)),
                active_requests=int(payload.get("activeRequests", 0)),
                in_flight_compute_units=int(payload.get("inFlightComputeUnits", 0)),
                weight=weight,
            )
        except (TimeoutError, HTTPError, URLError, ValueError):
            previous = self.states.get(server.id)
            if previous is not None:
                return ServerState(
                    id=previous.id,
                    base_url=previous.base_url,
                    online=False,
                    cpu_cores=previous.cpu_cores,
                    cpu_clock_ghz=previous.cpu_clock_ghz,
                    ram_gb=previous.ram_gb,
                    overhead_ms=previous.overhead_ms,
                    request_price=previous.request_price,
                    active_requests=previous.active_requests,
                    in_flight_compute_units=previous.in_flight_compute_units,
                    weight=previous.weight,
                )
            return ServerState(
                server.id, server.base_url, False, 0, 0, 0, 0, 0, 0, 0, server.weight
            )

    def _max_in_flight(self, state: ServerState) -> int:
        cap = self._capability(state)
        safe_weight = state.weight if state.weight > 0 else 1.0
        return max(1, int(round(cap * safe_weight * self.concurrency_capacity_factor)))

    def _rank_for_bin(
        self, bin_center: float, incoming_compute_units: float = 0.0
    ) -> List[tuple[ServerState, Dict[str, float]]]:
        ranked: List[tuple[ServerState, Dict[str, float]]] = []
        incoming = max(0.0, incoming_compute_units)
        for state in self.states.values():
            fit_ratio = self._capability(state) / bin_center
            p_sla = max(0.0, min(1.0, fit_ratio / self.sla_fit_threshold))
            cost = (state.overhead_ms * self.overhead_weight) + (state.request_price * self.price_weight)
            static_rank_score = (p_sla * 1000.0) - cost + (fit_ratio * 0.1)
            projected_active = state.active_requests + (1 if incoming > 0 else 0)
            active_part = projected_active / self.max_active_requests
            ewma = state.ewma_response_time_ms
            if ewma <= 0:
                ewma = self.target_response_time_ms
            rt_part = ewma / self.target_response_time_ms
            load_pressure = active_part + rt_part
            max_in_flight = self.max_active_requests
            rank_score = static_rank_score - (self.load_weight * load_pressure)
            ranked.append(
                (
                    state,
                    {
                        "fit_ratio": fit_ratio,
                        "p_sla": p_sla,
                        "cost": cost,
                        "static_rank_score": static_rank_score,
                        "active_requests": state.active_requests,
                        "in_flight_compute_units": state.in_flight_compute_units,
                        "max_in_flight": max_in_flight,
                        "weight": state.weight,
                        "load_pressure": load_pressure,
                        "rank_score": rank_score,
                    },
                )
            )

        ranked.sort(
            key=lambda item: (
                item[1]["load_pressure"],
                -item[1]["p_sla"],
                item[1]["cost"],
                -item[1]["fit_ratio"],
            )
        )
        return ranked

    def _build_log_bins(self) -> List[LoadBin]:
        bins: List[LoadBin] = []
        start = self.log_min_load
        while start <= self.log_max_load:
            end_exclusive = min(self.log_max_load + 1, start * self.log_base)
            center = (start * (end_exclusive - 1)) ** 0.5
            bins.append(
                LoadBin(
                    label=f"{start}-{end_exclusive - 1}",
                    min_inclusive=float(start),
                    max_exclusive=float(end_exclusive),
                    center=float(center),
                )
            )
            if end_exclusive >= self.log_max_load + 1:
                break
            start = end_exclusive
        return bins

    @staticmethod
    def _find_bin(bins: List[LoadBin], expected_compute_units: float) -> LoadBin:
        for b in bins:
            if b.contains(expected_compute_units):
                return b
        return bins[-1]

    def _capability(self, server: ServerState) -> float:
        cfg = next((s for s in self.servers if s.id == server.id), None)
        if cfg and cfg.capability_override and cfg.capability_override > 0:
            return cfg.capability_override
        return (server.cpu_cores * server.cpu_clock_ghz * 180.0) + (server.ram_gb * 22.0)

    @staticmethod
    def _notify_back_online(server: ServerState) -> None:
        print(
            "[NOTIFY] server back online:",
            server.id,
            {
                "cpuCores": server.cpu_cores,
                "cpuClockGhz": server.cpu_clock_ghz,
                "ramGb": server.ram_gb,
                "overheadMs": server.overhead_ms,
                "requestPrice": server.request_price,
            },
        )


def _normalize_server(raw: Dict[str, object]) -> ServerConfig:
    sid = str(raw["id"])
    base = raw.get("base_url") or raw.get("baseUrl")
    if base is None:
        raise ValueError("server entry requires base_url or baseUrl")
    info = raw.get("info_path") or raw.get("infoPath") or "/internal/node-info"
    weight = float(raw.get("weight", 1.0))
    if weight <= 0:
        weight = 1.0
    override_raw = raw.get("capabilityOverride") or raw.get("capability_override")
    override = float(override_raw) if override_raw is not None else None
    return ServerConfig(
        id=sid, base_url=str(base), info_path=str(info), weight=weight, capability_override=override
    )


def load_config(path: str) -> tuple[List[ServerConfig], Dict[str, float], Dict[str, int], int, int]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    servers = [_normalize_server(s) for s in data.get("servers", [])]
    weights = data.get("weights", {})
    route_compute = {str(k): int(v) for k, v in data.get("routeCompute", {}).items()}
    max_compute = int(data.get("maxComputeUnits", 2048))
    default_compute = int(data.get("defaultComputeUnits", 100))
    return servers, weights, route_compute, max_compute, default_compute


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to servers.json")
    parser.add_argument("--watch", action="store_true", help="Continuously poll and print status")
    parser.add_argument("--route", type=float, help="Expected compute units to route")
    parser.add_argument("--table", action="store_true", help="Print ranked table per load range")
    parser.add_argument("--interval", type=float, default=5.0, help="Polling interval seconds")
    args = parser.parse_args()

    servers, weights, _route, _max_c, _default_c = load_config(args.config)
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

    lb.refresh()
    if args.table:
        print(json.dumps(lb.table(), ensure_ascii=False, indent=2))
        return
    if args.route is not None:
        winner = lb.route(args.route)
        print(json.dumps({"selectedNodeId": winner.id, "baseUrl": winner.base_url}, ensure_ascii=False))
        return

    if args.watch:
        while True:
            lb.refresh()
            online = [s.id for s in lb.states.values() if s.online]
            offline = [s.id for s in lb.states.values() if not s.online]
            print(json.dumps({"online": online, "offline": offline}, ensure_ascii=False))
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
