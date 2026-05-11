from rest_framework import serializers
from .models import Invoice, InvoiceItem

class InvoiceSerializer(serializers.ModelSerializer):
    # لضمان عرض التاريخ فقط للقراءة
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Invoice
        fields = ['order_id', 'total_amount', 'created_at']

class InvoiceItemSerializer(serializers.ModelSerializer):
    # هذا السطر يسمح باستقبال رقم invoice_id في الطلب
    # ولكن داخلياً سيتم ربطه بالكائن (Object)
    invoice_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = InvoiceItem
        fields = ['invoice_id', 'product_name', 'quantity', 'price']