from django.urls import path

from .views import (
    LoadDistributionDecisionsView,
    LoadDistributionRouteView,
    LoadDistributionServersView,
    LoadDistributionTableView,
)

urlpatterns = []

load_distribution_urlpatterns = [
    path('servers', LoadDistributionServersView.as_view(), name='load-distribution-servers'),
    path('table', LoadDistributionTableView.as_view(), name='load-distribution-table'),
    path('decisions', LoadDistributionDecisionsView.as_view(), name='load-distribution-decisions'),
    path('route', LoadDistributionRouteView.as_view(), name='load-distribution-route'),
]
