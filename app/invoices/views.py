from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db import transaction, OperationalError
from .serializers import InvoiceSerializer, InvoiceItemSerializer
from .models import Invoice
from .tasks import process_purchase_order_task
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from .models import WeeklyReport

class CreateOrderView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceSerializer


    def create(self, request, *args, **kwargs):

        process_purchase_order_task.delay(request.user.id)

        return Response({"message": "Order is being processed"},status=status.HTTP_202_ACCEPTED )
    # def create(self, request, *args, **kwargs):
    #     # إعادة المحاولة تلقائياً عند تعارض قاعدة البيانات (3 محاولات)
    #     max_retries = 3
    #     for attempt in range(max_retries):
    #         try:
    #             return super().create(request, *args, **kwargs)
    #         except OperationalError as e:
    #             if 'could not serialize' in str(e).lower() and attempt < max_retries - 1:
    #                 continue
    #             raise

class InvoiceListView(generics.ListAPIView):
    serializer_class = InvoiceItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.filter(user=self.request.user).order_by('-created_at')
    

class WeeklyReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """آخر تقرير أسبوعي"""
        report = WeeklyReport.objects.first()
        if not report:
            return Response({"message": "No reports yet"}, status=404)

        return Response({
            "week": f"{report.week_start} to {report.week_end}",
            "total_sales": str(report.total_sales),
            "total_orders": report.total_orders,
            "total_items_sold": report.total_items_sold,
            "avg_order_value": str(report.avg_order_value),
            "top_product": report.top_product,
        })


class AllReportsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """كل التقارير"""
        reports = WeeklyReport.objects.all()[:12]  # آخر 12 أسبوع

        return Response([
            {
                "week": f"{r.week_start} to {r.week_end}",
                "sales": str(r.total_sales),
                "orders": r.total_orders,
            }
            for r in reports
        ])