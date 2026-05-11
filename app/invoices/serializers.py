from rest_framework import serializers
from .models import Invoice, InvoiceItem
from app.cart.models import Cart
from app.wallets.models import Wallet  # استيراد موديل المحفظة
from django.core.exceptions import ValidationError

class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['id', 'product_name', 'quantity', 'price']

class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    # هذا الحقل سيعرض الرصيد الحالي للمستخدم في الرد
    wallet_balance = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ['id', 'user', 'total_amount', 'status', 'created_at', 'items', 'wallet_balance']
        read_only_fields = ['id', 'user', 'created_at', 'status']

    def get_wallet_balance(self, obj):
        # دالة مساعدة لإرجاع رصيد المستخدم (تستخدم بعد إنشاء الفاتورة)
        try:
            return obj.user.wallet.balance
        except Wallet.DoesNotExist:
            return 0.00

    def validate(self, attrs):
        """
        التحقق قبل الحفظ: هل الرصيد يكفي؟
        """
        request = self.context.get('request')
        user = request.user

        # 1. التحقق من وجود محفظة
        try:
            wallet = user.wallet
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("لا توجد محفظة مرتبطة بهذا الحساب.")

        # 2. حساب إجمالي السلة
        cart_items = Cart.objects.filter(user=user)
        if not cart_items.exists():
            raise serializers.ValidationError("السلة فارغة، لا يمكن إنشاء فاتورة.")

        total_amount = sum(item.total_price() for item in cart_items)

        # 3. التحقق من كفاية الرصيد
        if wallet.balance < total_amount:
            raise serializers.ValidationError(
                f"عذراً، رصيد المحفظة غير كافٍ. المطلوب: {total_amount}، المتوفر: {wallet.balance}"
            )

        # نحفظ المبلغ الإجمالي في context لاستخدامه في دالة create لاحقاً
        self.context['total_amount'] = total_amount
        return attrs

    def create(self, validated_data):
        """
        إنشاء الفاتورة وخصم المبلغ
        """
        request = self.context.get('request')
        user = request.user
        total_amount = self.context.get('total_amount')
        
        # جلب السلة مرة أخرى (لأنها محسوبة سابقاً)
        cart_items = Cart.objects.filter(user=user)
        wallet = user.wallet

        # 1. خصم المبلغ من المحفظة
        wallet.balance -= total_amount
        wallet.save()

        # 2. إنشاء الفاتورة
        invoice = Invoice.objects.create(
            user=user,
            total_amount=total_amount,
            status='pending' 
        )

        # 3. نقل المنتجات إلى InvoiceItem
        for item in cart_items:
            InvoiceItem.objects.create(
                invoice=invoice,
                product_name=item.products_id.name,
                quantity=item.quantity,
                price=item.products_id.price
            )
            
            # (اختياري) تحديث المخزون
            product = item.products_id
            product.stock -= item.quantity
            product.save()

        # 4. تفريغ السلة
        cart_items.delete()

        return invoice