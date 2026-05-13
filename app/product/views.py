from rest_framework import generics
from .models import Product
from .serializers import ProductSerializer

# View لعرض قائمة المنتجات المتوفرة فقط
class ProductListView(generics.ListAPIView):
    # تعديل الـ Queryset: استبعاد المنتجات التي مخزونها 0 أو أقل
    # نستخدم filter لمنع العرض
    queryset = Product.objects.filter(stock__gt=0) # gt = Greater Than (أكبر من 0)
    serializer_class = ProductSerializer

# View لعرض تفاصيل منتج محدد
class ProductDetailView(generics.RetrieveAPIView):
    # يمكنك تركها تعرض كل المنتجات، أو تصفيتها هنا أيضاً
    queryset = Product.objects.all()
    serializer_class = ProductSerializer