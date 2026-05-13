from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import InvoiceSerializer
from .models import Invoice
from .tasks import process_purchase_order_task

class CreateOrderView(generics.CreateAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # 1. التحقق البسيط (يمكن وضع التحقق هنا لتوفير الوقت في حال السلة فارغة)
        serializer = self.get_serializer(data={})
        serializer.is_valid(raise_exception=True)

        # 2. إرسال الأمر لـ Celery (إدخال الطابور)
        # delay() يعني نفذها في الخلفية وارجع فوراً رد للعميل
        task_result = process_purchase_order_task.delay(request.user.id)

        return Response({
            "message": "تم استلام طلبك. يرجى الانتظار بينما يتم معالجته...",
            "task_id": task_result.id, # يمكن استخدامه لتتبع الحالة
            "status": "processing_queue"
        }, status=status.HTTP_202_ACCEPTED)

class InvoiceListView(generics.ListAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.filter(user=self.request.user).order_by('-created_at')