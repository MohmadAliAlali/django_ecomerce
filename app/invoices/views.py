from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import InvoiceSerializer
from .models import Invoice

class CreateOrderView(generics.CreateAPIView):
    """
    ينشئ فاتورة جديدة، يتحقق من الرصيد، ويخصم المبلغ
    """
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        """
        تمرير الـ request للـ Serializer لاستخدامه في جلب المستخدم والمحفظة
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data={})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        return Response(
            {
                "message": "تم إنشاء الطلب وخصم المبلغ بنجاح",
                "invoice": serializer.data
            }, 
            status=status.HTTP_201_CREATED, 
            headers=headers
        )

class InvoiceListView(generics.ListAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.filter(user=self.request.user).order_by('-created_at')