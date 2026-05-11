from django.urls import path
from .views import WalletDetailView, WalletAddFundsView

urlpatterns = [
    path('my-wallet/', WalletDetailView.as_view(), name='wallet-detail'),
    path('add-funds/', WalletAddFundsView.as_view(), name='wallet-add-funds'),
]