import logging
import time

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from app.common.performance_monitor import _record

logger = logging.getLogger('performance')


class PerformanceMonitorMiddleware(MiddlewareMixin):
    """Log API request duration (complements service-layer @monitor_execution)."""

    def process_request(self, request):
        if not getattr(settings, 'PERFORMANCE_MONITOR_ENABLED', True):
            return None
        if not request.path.startswith('/api/'):
            return None
        request._perf_started_at = time.perf_counter()
        return None

    def process_response(self, request, response):
        started = getattr(request, '_perf_started_at', None)
        if started is None:
            return response

        elapsed_ms = (time.perf_counter() - started) * 1000
        label = f'http.{request.method}.{request.path}'
        _record(label, elapsed_ms)

        threshold = getattr(settings, 'PERFORMANCE_MONITOR_SLOW_MS', 200)
        if elapsed_ms >= threshold:
            logger.warning('%s -> %s in %.2fms', request.method, request.path, elapsed_ms)
        else:
            logger.debug('%s -> %s in %.2fms', request.method, request.path, elapsed_ms)
        return response
