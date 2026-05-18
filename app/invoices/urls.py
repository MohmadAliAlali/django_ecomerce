from django.urls import path
from .views import CreateOrderView, InvoiceListView , WeeklyReportView, AllReportsView

urlpatterns = [
    path('create/', CreateOrderView.as_view(), name='create-order'),
    path('list/', InvoiceListView.as_view(), name='invoice-list'),
        path('report/weekly/', WeeklyReportView.as_view(), name='weekly-report'),
    path('report/all/', AllReportsView.as_view(), name='all-reports'),
]