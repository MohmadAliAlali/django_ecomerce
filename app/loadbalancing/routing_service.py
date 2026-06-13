import json
import os
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from app.loadbalancing.node_info import node_info_payload


def _scripts_dir() -> Path:
    return Path(getattr(settings, 'LB_SCRIPTS_DIR', settings.BASE_DIR / 'scripts'))


@lru_cache(maxsize=1)
def _load_balancer():
    import sys

    scripts = str(_scripts_dir())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    from custom_load_balancer import CustomLoadBalancer, load_config

    config_path = getattr(
        settings,
        'LB_SERVERS_CONFIG',
        _scripts_dir() / 'servers.django.json',
    )
    servers, weights, route_compute, max_compute, default_compute = load_config(str(config_path))
    lb = CustomLoadBalancer(
        servers=servers,
        overhead_weight=float(weights.get('overheadWeight', 0.40)),
        price_weight=float(weights.get('priceWeight', 1.20)),
        underpowered_penalty=float(weights.get('underpoweredPenalty', 0.35)),
        sla_fit_threshold=float(weights.get('slaFitThreshold', 1.0)),
        log_min_load=int(weights.get('logMinLoad', 1)),
        log_max_load=int(weights.get('logMaxLoad', 2048)),
        log_base=int(weights.get('logBase', 2)),
        load_weight=float(weights.get('loadWeight', 25.0)),
        concurrency_capacity_factor=float(weights.get('concurrencyCapacityFactor', 1.0)),
    )
    return lb, route_compute, max_compute, default_compute


def server_snapshots() -> list[dict]:
    lb, _, _, _ = _load_balancer()
    lb.refresh()
    snapshots = []
    for state in lb.states.values():
        snapshots.append({
            'id': state.id,
            'online': state.online,
            'cpuCores': state.cpu_cores,
            'cpuClockGhz': state.cpu_clock_ghz,
            'ramGb': state.ram_gb,
            'overheadMs': state.overhead_ms,
            'requestPrice': state.request_price,
            'activeRequests': state.active_requests,
            'inFlightComputeUnits': state.in_flight_compute_units,
            'ewmaResponseTimeMs': state.ewma_response_time_ms,
            'baseUrl': state.base_url,
        })
    local = node_info_payload()
    snapshots.append({
        'id': local['nodeId'],
        'online': local['availableForRequests'],
        'cpuCores': local['cpuCores'],
        'cpuClockGhz': local['cpuClockGhz'],
        'ramGb': local['ramGb'],
        'overheadMs': local['overheadMs'],
        'requestPrice': local['requestPrice'],
        'activeRequests': local['activeRequests'],
        'inFlightComputeUnits': local['inFlightComputeUnits'],
        'ewmaResponseTimeMs': local['ewmaResponseTimeMs'],
        'baseUrl': 'self',
    })
    return snapshots


def route_decision(expected_compute_units: float) -> dict:
    lb, _, _, _ = _load_balancer()
    lb.refresh()
    chosen = lb.route(expected_compute_units)
    return {
        'serverId': chosen.id,
        'baseUrl': chosen.base_url,
        'online': chosen.online,
        'expectedComputeUnits': expected_compute_units,
    }


def routing_table_snapshot() -> dict:
    lb, _, _, _ = _load_balancer()
    lb.refresh()
    return lb.table()


def bin_decisions_snapshot() -> list[dict]:
    cache_file = getattr(settings, 'LB_ROUTING_CACHE_FILE', None)
    if cache_file and os.path.exists(cache_file):
        with open(cache_file, encoding='utf-8') as handle:
            payload = json.load(handle)
        return payload.get('routes', [])
    return []
