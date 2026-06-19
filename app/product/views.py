from django.http import Http404
from django.conf import settings
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .catalog_cache import get_product_cached
from .models import Product
from .serializers import ProductItemSerializer, ProductSerializer


class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    queryset = Product.objects.filter(stock__gt=0)
    serializer_class = ProductSerializer


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = Product.objects.all()
    serializer_class = ProductItemSerializer

    def retrieve(self, request, *args, **kwargs):
        product_id = kwargs.get(self.lookup_field or 'pk')
        bypass = (
            getattr(settings, 'PERFORMANCE_BENCHMARK_ALLOW_BYPASS', False)
            and request.headers.get('X-Bypass-Product-Cache') == '1'
        )
        cached = get_product_cached(int(product_id), bypass_cache=bypass)
        if cached is None:
            raise Http404('Product not found')
        return Response(cached)
