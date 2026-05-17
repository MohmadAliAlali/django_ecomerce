from django.urls import path, include

from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import LoginView, SignupCreateAPIView

router = DefaultRouter()




urlpatterns = [
    path('login/', LoginView.as_view(), name='api_token_auth'),
    path('signup/', SignupCreateAPIView.as_view(), name='signup'),

]