from django.conf import settings
from django.core.cache import cache

from app.product.models import Product
from app.product.serializers import ProductItemSerializer

PRODUCT_CACHE_PREFIX = 'product:'


def _cache_key(product_id: int) -> str:
    return f'{PRODUCT_CACHE_PREFIX}{product_id}'


def get_product_cached(product_id: int):
    """Cache-aside read for hot product detail paths (course req #6)."""
    key = _cache_key(product_id)
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return None

    payload = ProductItemSerializer(product).data
    cache.set(key, payload, timeout=getattr(settings, 'PRODUCT_CACHE_TTL', 300))
    return payload


def evict_product(product_id: int) -> None:
    cache.delete(_cache_key(product_id))
