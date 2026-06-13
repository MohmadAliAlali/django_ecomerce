from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice, WeeklyReport
from .serializers import InvoiceItemSerializer, InvoiceSerializer


class CreateOrderView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class InvoiceListView(generics.ListAPIView):
    serializer_class = InvoiceItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.filter(user=self.request.user).order_by('-created_at')


class WeeklyReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        report = WeeklyReport.objects.first()
        if not report:
            return Response({'message': 'No reports yet'}, status=404)

        return Response({
            'week': f'{report.week_start} to {report.week_end}',
            'total_sales': str(report.total_sales),
            'total_orders': report.total_orders,
            'total_items_sold': report.total_items_sold,
            'avg_order_value': str(report.avg_order_value),
            'top_product': report.top_product,
        })


class AllReportsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        reports = WeeklyReport.objects.all()[:12]
        return Response([
            {
                'week': f'{r.week_start} to {r.week_end}',
                'sales': str(r.total_sales),
                'orders': r.total_orders,
            }
            for r in reports
        ])
