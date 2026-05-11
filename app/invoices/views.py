# invoices/views.py
from rest_framework import viewsets, status
from rest_framework.generics import CreateAPIView, RetrieveAPIView, DestroyAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .viewmodel import InvoiceViewModel, InvoiceItemViewModel
from .serializers import InvoiceSerializer, InvoiceItemSerializer
from .models import Invoice, InvoiceItem

class InvoicesViewSet(CreateAPIView, RetrieveAPIView, DestroyAPIView):

    # permission_classes = [IsAuthenticated]

    def list(self, request):
        # 1. جلب الفواتير الخاصة بالمستخدم فقط
        invoices = Invoice.objects.filter(user=request.user)
        
        # 2. تحويل البيانات لـ JSON
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def create(self, request):
        # 1. إنشاء الـ ViewModel وتمرير الـ request للـ context (ضروري لمعرفة المستخدم)
        view_model = InvoiceViewModel(data=request.data, context={'request': request})
        
        # 2. تنفيذ العملية (التحقق والحفظ والمعالجة)
        result = view_model.execute()
        
        # 3. إرجاع الرد
        return Response(result['data'], status=result['status'])
    
    def retrieve(self, request, pk=None):
        # لعرض فاتورة واحدة بالتفاصيل
        try:
            invoice = Invoice.objects.get(pk=pk, user=request.user)
            serializer = InvoiceSerializer(invoice)
            return Response(serializer.data)
        except Invoice.DoesNotExist:
            return Response({'error': 'Invoice not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def destroy(self, request, pk=None):
        # لحذف الفاتورة
        try:
            invoice = Invoice.objects.get(pk=pk, user=request.user)
            invoice.delete()
            return Response({'message': 'Invoice deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except Invoice.DoesNotExist:
            return Response({'error': 'Invoice not found'}, status=status.HTTP_404_NOT_FOUND)


class InvoiceItemsViewSet(viewsets.ViewSet):
    """
    مسئول عن عرض وإضافة عناصر الفواتير
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        # جلب الفواتير التي يملكها المستخدم أولاً
        user_invoices = Invoice.objects.filter(user=request.user)
        
        # ثم جلب العناصر المرتبطة بهذه الفواتير
        items = InvoiceItem.objects.filter(invoice__in=user_invoices)
        
        serializer = InvoiceItemSerializer(items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def create(self, request):
        # إنشاء عنصر جديد باستخدام الـ ViewModel
        view_model = InvoiceItemViewModel(data=request.data, context={'request': request})
        result = view_model.execute()
        return Response(result['data'], status=result['status'])
    
    def destroy(self, request, pk=None):
        # حذف عنصر (مع التأكد أن الفاتورة تابعة للمستخدم)
        try:
            # نبحث عن العنصر
            item = InvoiceItem.objects.get(pk=pk)
            
            # نتأكد أن الفاتورة التي يحتويها العنصر تابعة للمستخدم الحالي
            if item.invoice.user != request.user:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
                
            item.delete()
            return Response({'message': 'Invoice item deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
            
        except InvoiceItem.DoesNotExist:
            return Response({'error': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)