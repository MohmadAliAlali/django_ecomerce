from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from app.cart.models import Cart
from app.product.catalog_cache import evict_product
from app.product.models import Product
from app.wallets.models import Wallet

from .models import Invoice, InvoiceItem


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
            return Decimal('0.00')

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user

        try:
            wallet = user.wallet
        except Wallet.DoesNotExist:
            raise serializers.ValidationError('لا توجد محفظة مرتبطة بهذا الحساب.')

        cart_items = list(Cart.objects.filter(user=user).select_related('products_id'))
        if not cart_items:
            raise serializers.ValidationError('السلة فارغة.')

        total_amount = sum(item.total_price() for item in cart_items)
        if wallet.balance < total_amount:
            raise serializers.ValidationError(
                f'رصيد غير كافٍ. المطلوب: {total_amount}، المتوفر: {wallet.balance}'
            )

        self.context['total_amount'] = total_amount
        self.context['cart_items'] = sorted(cart_items, key=lambda item: item.products_id_id)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        Checkout with pessimistic row locks on wallet and products (course req #7).
        Cart lines are sorted by product id to reduce deadlocks.
        """
        request = self.context.get('request')
        user = request.user
        total_amount = self.context.get('total_amount')
        cart_items = self.context.get('cart_items')

        wallet = Wallet.objects.select_for_update().get(user=user)
        if wallet.balance < total_amount:
            raise serializers.ValidationError(
                'رصيد المحفظة غير كافٍ أو تم استهلاكه في طلب آخر.'
            )

        wallet.balance -= total_amount
        wallet.version += 1
        wallet.save(update_fields=['balance', 'version'])

        invoice = Invoice.objects.create(
            user=user,
            total_amount=total_amount,
            status='pending',
        )

        for item in cart_items:
            product = Product.objects.select_for_update().get(pk=item.products_id_id)
            if product.stock < item.quantity:
                raise serializers.ValidationError(
                    f'نفد المخزون للمنتج {product.name}. '
                    f'المتوفر: {product.stock}، المطلوب: {item.quantity}'
                )

            product.stock -= item.quantity
            product.version += 1
            product.save(update_fields=['stock', 'version'])
            evict_product(product.pk)

            InvoiceItem.objects.create(
                invoice=invoice,
                product_name=product.name,
                quantity=item.quantity,
                price=product.price,
            )

        Cart.objects.filter(user=user).delete()
        invoice.status = 'access'
        invoice.save(update_fields=['status'])
        return invoice
