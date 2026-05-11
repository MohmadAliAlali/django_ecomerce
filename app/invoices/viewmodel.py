# viewmodels.py
from helper.viewmodel import BaseViewModel  # تأكد من وجود المسار الصحيح للفئة الأساسية
from .serializers import InvoiceItemSerializer, InvoiceSerializer
from .models import Invoice
from django.db import IntegrityError

class InvoiceViewModel(BaseViewModel):
    serializer_class = InvoiceSerializer

    def perform_action(self):
        # نقوم بالحفظ وربط المستخدم الحالي بالفاتورة
        # نحتاج التأكد من أن request موجود في context
        request = self.context.get('request')
        if not request:
            raise Exception("Request context is required")
            
        invoice = self.serializer.save(user=request.user)        
        return {'invoice_id': invoice.id, 'message': 'Invoice created successfully'}
    
class InvoiceItemViewModel(BaseViewModel):
    serializer_class = InvoiceItemSerializer

    def perform_action(self):
        # استخراج البيانات المتحقق منها
        validated_data = self.serializer.validated_data
        invoice_id = validated_data.pop('invoice_id') # أخذ رقم الفاتورة وحذفه من القاموس
        
        try:
            # البحث عن الفاتورة
            invoice = Invoice.objects.get(id=invoice_id)
            
            # الحفظ مع ربط الكائن (invoice) بدلاً من الرقم
            invoice_item = self.serializer.save(invoice=invoice)        
            return {
                'invoice_item_id': invoice_item.id, 
                'message': 'Invoice item created successfully'
            }
        except Invoice.DoesNotExist:
            raise IntegrityError("Invoice not found")