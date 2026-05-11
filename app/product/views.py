from rest_framework import generics
from .models import Product
from .serializers import ProductSerializer

# View لعرض قائمة بجميع المنتجات
class ProductListView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

# View لعرض تفاصيل منتج محدد (عن طريق الـ ID في الرابط)
class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer