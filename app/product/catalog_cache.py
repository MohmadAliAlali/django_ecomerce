from django.conf import settings
from django.core.cache import cache

from app.common.performance_monitor import monitor_execution
from app.product.models import Product
from app.product.serializers import ProductItemSerializer

PRODUCT_CACHE_PREFIX = 'product:'


def _cache_key(product_id: int) -> str:
    return f'{PRODUCT_CACHE_PREFIX}{product_id}'


def _load_from_db(product_id: int):
    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return None
    return ProductItemSerializer(product).data


@monitor_execution('product.get_product_cached')
def get_product_cached(product_id: int, *, bypass_cache: bool = False):
    """Cache-aside read for hot product detail paths (course req #6)."""
    if bypass_cache or not getattr(settings, 'PRODUCT_CACHE_ENABLED', True):
        return _load_from_db(product_id)

    key = _cache_key(product_id)
    cached = cache.get(key)
    if cached is not None:
        return cached

    payload = _load_from_db(product_id)
    if payload is not None:
        cache.set(key, payload, timeout=getattr(settings, 'PRODUCT_CACHE_TTL', 300))
    return payload


def evict_product(product_id: int) -> None:
    cache.delete(_cache_key(product_id))
