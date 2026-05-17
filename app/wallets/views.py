from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Wallet
from .serializers import WalletSerializer, WalletTransactionSerializer

class WalletDetailView(generics.RetrieveAPIView):
    """
    لعرض رصيد المحفظة الحالي
    """
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # جلب محفظة المستخدم الحالي
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet

class WalletAddFundsView(generics.UpdateAPIView):
    """
    لزيادة رصيد المحفظة (شحن)
    """
    serializer_class = WalletTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # جلب محفظة المستخدم المراد شحنها
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        # استخدام TransactionSerializer لمعالجة المنطق
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response({
            "message": "تم شحن الرصيد بنجاح",
            "new_balance": serializer.instance.balance
        }, status=status.HTTP_200_OK)