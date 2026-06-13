import time

from django.utils.deprecation import MiddlewareMixin

from app.loadbalancing.node_info import node_id, publish_live_state
from app.loadbalancing.route_compute import resolve_compute_units
from app.loadbalancing.tracking import ewma_tracker, tracker


class ServedByMiddleware(MiddlewareMixin):
    header_name = 'X-Served-By'

    def process_response(self, request, response):
        response[self.header_name] = node_id()
        return response


class RequestConcurrencyMiddleware(MiddlewareMixin):
    compute_header = 'X-Compute-Units'

    def process_request(self, request):
        if not request.path.startswith('/api/'):
            return None

        compute_units = resolve_compute_units(
            request.path,
            request.META.get('HTTP_X_COMPUTE_UNITS'),
        )
        request._lb_compute_units = compute_units
        request._lb_started_at = time.perf_counter()
        tracker.on_request_started(compute_units)
        publish_live_state()
        return None

    def process_response(self, request, response):
        if not request.path.startswith('/api/'):
            return response

        compute_units = getattr(request, '_lb_compute_units', 1)
        started = getattr(request, '_lb_started_at', None)
        if started is not None:
            duration_ms = int((time.perf_counter() - started) * 1000)
            ewma_tracker.record(duration_ms)

        tracker.on_request_finished(compute_units)
        publish_live_state()
        return response
