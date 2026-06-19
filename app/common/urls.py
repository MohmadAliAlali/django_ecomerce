from django.urls import path

from app.common.views import HealthView, PerformanceStatsView

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path('performance/stats/', PerformanceStatsView.as_view(), name='performance-stats'),
]
