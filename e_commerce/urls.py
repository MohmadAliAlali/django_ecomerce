from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
# from django_psutil_dash.urls import psutil_urlpatterns 


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/accounts/', include('app.accounts.urls')),
    path('api/products/', include('app.product.urls')),
    path('api/cart/', include('app.cart.urls')),
    path('api/invoices/', include('app.invoices.urls')),
    path('api/wallets/', include('app.wallets.urls')),
    

    # path('silk/', include('silk.urls', namespace='silk')),  
    # path('system/', psutil_urlpatterns()),                 
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]