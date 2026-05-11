from django.urls import path
from .views import *








urlpatterns = [
    # إنشاء سلة (POST)
    path('inv/', InvoicesViewSet.as_view(), name='inv-create'),
    
]