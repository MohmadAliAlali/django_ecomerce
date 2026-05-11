from django.urls import path, include

from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import * 

router = DefaultRouter()




# router.register(r'auth', views.AuthViewSet, basename='auth')
# router.register(r'signup', views.SignupViewSet, basename='signup')

# 3. إضافة الروابط التي أنشأها الـ Router إلى urlpatterns
urlpatterns = [
    # path('', include(router.urls)),
    path('login/', LoginView.as_view(), name='api_token_auth'),
    path('signup/', SignupCreateAPIView.as_view(), name='signup'),

]