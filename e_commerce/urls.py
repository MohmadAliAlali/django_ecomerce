from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from app.loadbalancing.urls import load_distribution_urlpatterns
from app.loadbalancing.views import NodeInfoView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('internal/node-info', NodeInfoView.as_view(), name='node-info'),
    path('api/load-distribution/', include(load_distribution_urlpatterns)),
    path('api/accounts/', include('app.accounts.urls')),
    path('api/products/', include('app.product.urls')),
    path('api/cart/', include('app.cart.urls')),
    path('api/invoices/', include('app.invoices.urls')),
    path('api/wallets/', include('app.wallets.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]