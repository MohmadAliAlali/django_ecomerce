from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db import transaction, OperationalError
from .serializers import InvoiceSerializer, InvoiceItemSerializer
from .models import Invoice
from .tasks import process_purchase_order_task

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