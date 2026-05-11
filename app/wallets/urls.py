# app/wallets/urls.py
from django.urls import path
from .views import WalletCreateView

urlpatterns = [
    # تسجيل العرض مباشرة باستخدام path
    path('create/', WalletCreateView.as_view(), name='wallet-create'),
]