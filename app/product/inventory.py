from django.db import transaction
from django.db.models import F

from app.common.exceptions import BusinessRuleError, ConcurrentUpdateError
from app.common.performance_monitor import monitor_execution
from app.product.catalog_cache import evict_product
from app.product.models import Product


@monitor_execution('product.adjust_stock')
def adjust_stock(product_id: int, delta: int) -> Product:
    """
    Lower-contention stock adjustment using optimistic locking via version field.
    Mirrors Spring InventoryService.adjustStock.
    """
    with transaction.atomic():
        product = Product.objects.filter(pk=product_id).first()
        if product is None:
            raise BusinessRuleError(f'Product not found: {product_id}')

        expected_version = product.version
        next_stock = product.stock + delta
        if next_stock < 0:
            raise BusinessRuleError(f'Insufficient stock for product: {product_id}')

        updated = Product.objects.filter(pk=product_id, version=expected_version).update(
            stock=next_stock,
            version=F('version') + 1,
        )
        if updated == 0:
            raise ConcurrentUpdateError()

        product.refresh_from_db()
        evict_product(product_id)
        return product
