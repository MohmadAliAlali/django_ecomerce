from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app.common.performance_monitor import get_stats_snapshot, reset_stats


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({'status': 'UP', 'service': 'django-ecommerce'})


class PerformanceStatsView(APIView):
    """Expose aggregated service/request timings for bottleneck analysis."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(get_stats_snapshot())

    def delete(self, request):
        reset_stats()
        return Response({'reset': True})
