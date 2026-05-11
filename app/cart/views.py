from rest_framework import status
from rest_framework.generics import CreateAPIView, RetrieveAPIView, DestroyAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import CartSerializer
from .models import Cart
class CartCreateView(CreateAPIView):
    """
    العرض أصبح نظيفاً جداً
    """
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        """
        خطوة مهمة جداً لتمرير الـ request إلى الـ Serializer
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class CartDetailView(RetrieveAPIView):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):

        return Cart.objects.get(user=self.request.user)


class CartDeleteView(DestroyAPIView):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return Cart.objects.get(user=self.request.user)