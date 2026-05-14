from rest_framework import generics
from .models import Product
from rest_framework.permissions import AllowAny
from .serializers import ProductSerializer

# View لعرض قائمة المنتجات المتوفرة فقط
class ProductListView(generics.ListAPIView):
    # تعديل الـ Queryset: استبعاد المنتجات التي مخزونها 0 أو أقل
    # نستخدم filter لمنع العرض
    permission_classes = [AllowAny]
    queryset = Product.objects.filter(stock__gt=0) # gt = Greater Than (أكبر من 0)
    serializer_class = ProductSerializer

# View لعرض تفاصيل منتج محدد
class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    # يمكنك
    #  تركها تعرض كل المنتجات، أو تصفيتها هنا أيضاً
    queryset = Product.objects.all()
    serializer_class = ProductSerializer