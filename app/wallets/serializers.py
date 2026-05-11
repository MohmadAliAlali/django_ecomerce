from rest_framework import serializers
from .models import Wallet
from django.core.exceptions import ValidationError

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['id', 'user', 'balance']
        read_only_fields = ['id', 'user', 'balance']

class WalletTransactionSerializer(serializers.Serializer):
    """
    هذا Serializer يستخدم لعملية الشحن (إضافة رصيد)
    """
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("يجب أن يكون المبلغ أكبر من صفر.")
        return value

    def update(self, instance, validated_data):
        """
        يقوم بتحديث رصيد المحفظة (إضافة المبلغ)
        """
        amount_to_add = validated_data.get('amount')
        instance.balance += amount_to_add
        instance.save()
        return instance