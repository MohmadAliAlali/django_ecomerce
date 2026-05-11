from django.urls import path
from .views import CreateOrderView, InvoiceListView

urlpatterns = [
    path('create/', CreateOrderView.as_view(), name='create-order'),
    path('list/', InvoiceListView.as_view(), name='invoice-list'),
]