from django.db import transaction
from rest_framework import serializers

from app.wallets.models import Wallet


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['id', 'user', 'balance', 'version']
        read_only_fields = ['id', 'user', 'balance', 'version']


class WalletTransactionSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('يجب أن يكون المبلغ أكبر من صفر.')
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        wallet = Wallet.objects.select_for_update().get(pk=instance.pk)
        amount_to_add = validated_data.get('amount')
        wallet.balance += amount_to_add
        wallet.version += 1
        wallet.save(update_fields=['balance', 'version'])
        return wallet
