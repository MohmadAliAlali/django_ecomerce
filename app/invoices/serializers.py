from rest_framework import serializers
from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError

from app.product.models import Product
from .models import Invoice, InvoiceItem
from app.cart.models import Cart
from app.wallets.models import Wallet

class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['id', 'product_name', 'quantity', 'price']

class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    wallet_balance = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ['id', 'user', 'total_amount', 'status', 'created_at', 'items', 'wallet_balance']
        read_only_fields = ['id', 'user', 'created_at', 'status']

    def get_wallet_balance(self, obj):
        try:
            return obj.user.wallet.balance
        except Wallet.DoesNotExist:
            return 0.00

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user

        try:
            wallet = user.wallet
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("لا توجد محفظة مرتبطة بهذا الحساب.")

        cart_items = Cart.objects.filter(user=user)
        if not cart_items.exists():
            raise serializers.ValidationError("السلة فارغة.")

        total_amount = sum(item.total_price() for item in cart_items)

        # تحقق أولي سريع (التحقق الحاسم يحدث في create عبر F())
        if wallet.balance < total_amount:
            raise serializers.ValidationError(
                f"رصيد غير كافٍ. المطلوب: {total_amount}، المتوفر: {wallet.balance}"
            )

        self.context['total_amount'] = total_amount
        self.context['cart_items'] = list(cart_items)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        إنشاء الفاتورة باستخدام Optimistic Locking عبر F() + filter.
        لا يوجد select_for_update() — لا يوجد قفل على الصفوف.
        """
        request = self.context.get('request')
        user = request.user
        total_amount = self.context.get('total_amount')
        cart_items = self.context.get('cart_items')

        # ═══════════════════════════════════════════════════
        # 💰 الخطوة 1: خصم المحفظة (ذري + شرطي)
        # ═══════════════════════════════════════════════════
        # filter(balance__gte=...) يضمن: إما أن يكفي الرصيد، أو لا يحدث شيء
        updated_wallets = Wallet.objects.filter(
            user=user,
            balance__gte=total_amount          # ← الشرط: الرصيد يكفي
        ).update(
            balance=F('balance') - total_amount  # ← العملية الذرية في PostgreSQL
        )

        if updated_wallets == 0:
            # إما رصيد غير كافٍ، أو طلب آخر عدّله في هذه اللحظة
            raise serializers.ValidationError(
                "رصيد المحفظة غير كافٍ أو تم استهلاكه في طلب آخر."
            )

        # ═══════════════════════════════════════════════════
        # 🧾 الخطوة 2: إنشاء الفاتورة
        # ═══════════════════════════════════════════════════
        invoice = Invoice.objects.create(
            user=user,
            total_amount=total_amount,
            status='pending'
        )

        # ═══════════════════════════════════════════════════
        # 📦 الخطوة 3: خصم مخزون كل منتج (ذري + شرطي)
        # ═══════════════════════════════════════════════════
        for item in cart_items:
            updated_products = Product.objects.filter(
                pk=item.products_id.pk,
                stock__gte=item.quantity         # ← الشرط: المخزون يكفي
            ).update(
                stock=F('stock') - item.quantity   # ← العملية الذرية
            )

            if updated_products == 0:
                # فشل: إما نفد المخزون أو تم استهلاكه من طلب آخر
                # transaction.atomic سيلغي كل شيء تلقائياً (بما في ذلك رصيد المحفظة)
                product = Product.objects.get(pk=item.products_id.pk)
                if product.stock < item.quantity:
                    raise serializers.ValidationError(
                        f"نفد المخزون للمنتج {product.name}. "
                        f"المتوفر: {product.stock}، المطلوب: {item.quantity}"
                    )
                else:
                    raise serializers.ValidationError(
                        f"تعارض في تحديث المنتج {product.name}. أعد المحاولة."
                    )

            # إنشاء سجل الفاتورة
            InvoiceItem.objects.create(
                invoice=invoice,
                product_name=item.products_id.name,
                quantity=item.quantity,
                price=item.products_id.price
            )

        # ═══════════════════════════════════════════════════
        # 🗑️ الخطوة 4: تفريغ السلة
        # ═══════════════════════════════════════════════════
        Cart.objects.filter(user=user).delete()

        return invoice