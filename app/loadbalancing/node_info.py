import os
import time

from django.conf import settings

from app.loadbalancing.server_tier import ServerTier
from app.loadbalancing.tracking import ewma_tracker, tracker


def node_id() -> str:
    configured = os.getenv('NODE_ID') or getattr(settings, 'LB_NODE_ID', 'local')
    return configured.strip() or 'local'

def node_info_payload() -> dict:
    tier = ServerTier.from_env(os.getenv('SERVER_TIER') or getattr(settings, 'LB_SERVER_TIER', 'MEDIUM'))
    node = getattr(settings, 'LB_NODE_INFO', {})
    effective_ewma = max(ewma_tracker.ewma_millis, tier.target_response_time_ms)
    return {
        'nodeId': node_id(),
        'availableForRequests': node.get('available_for_requests', True),
        'cpuCores': node.get('cpu_cores', 4.0),
        'cpuClockGhz': node.get('cpu_clock_ghz', 2.8),
        'ramGb': node.get('ram_gb', 8.0),
        'overheadMs': node.get('overhead_ms', 12.0),
        'requestPrice': node.get('request_price', 0.025),
        'activeRequests': tracker.active_requests,
        'inFlightComputeUnits': tracker.in_flight_compute_units,
        'ewmaResponseTimeMs': effective_ewma,
        'serverTier': tier.name,
        'maxActiveRequests': tier.max_active_requests,
        'targetResponseTimeMs': tier.target_response_time_ms,
    }


def publish_live_state() -> None:
    current_node = node_id()
    if not current_node or current_node == 'local':
        return

    try:
        import redis
    except ImportError:
        return

    tier = ServerTier.from_env(os.getenv('SERVER_TIER') or getattr(settings, 'LB_SERVER_TIER', 'MEDIUM'))
    payload = node_info_payload()
    ttl_seconds = max(1, int(getattr(settings, 'LB_REDIS_LIVE_STATE_TTL_SECONDS', 1)))

    client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'redis'),
        port=int(os.getenv('REDIS_PORT', '6379')),
        db=0,
        decode_responses=True,
        socket_timeout=0.2,
    )
    key = f'lb:live:{current_node}'
    now_ms = int(time.time() * 1000)
    client.hset(
        key,
        mapping={
            'active': str(payload['activeRequests']),
            'inFlight': str(payload['inFlightComputeUnits']),
            'ewmaRtMs': str(payload['ewmaResponseTimeMs']),
            'online': '1' if payload['availableForRequests'] else '0',
            'updatedAt': str(now_ms),
            'maxActive': str(tier.max_active_requests),
            'targetRtMs': str(tier.target_response_time_ms),
            'serverTier': tier.name,
        },
    )
    client.expire(key, ttl_seconds)
