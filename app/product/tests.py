from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.common.exceptions import ConcurrentUpdateError
from app.product.catalog_cache import get_product_cached
from app.product.inventory import adjust_stock
from app.product.models import Product


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
)
class ProductCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.product = Product.objects.create(
            name='Cached Widget',
            description='Test',
            price=Decimal('10.00'),
            stock=5,
        )

    def test_second_read_uses_cache(self):
        with self.assertNumQueries(1):
            first = get_product_cached(self.product.id)
        self.assertEqual(first['name'], 'Cached Widget')

        with patch('app.product.catalog_cache.Product.objects.get') as mocked_get:
            second = get_product_cached(self.product.id)
            mocked_get.assert_not_called()
        self.assertEqual(second['name'], 'Cached Widget')


class OptimisticStockTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Optimistic Widget',
            description='Test',
            price=Decimal('5.00'),
            stock=10,
        )

    def test_adjust_stock_increments_version(self):
        updated = adjust_stock(self.product.id, 3)
        self.assertEqual(updated.stock, 13)
        self.assertEqual(updated.version, 1)

    def test_concurrent_adjust_raises(self):
        product = Product.objects.get(pk=self.product.pk)
        product.version = 0
        with patch('app.product.inventory.Product.objects.filter') as mock_filter:
            mock_filter.return_value.first.return_value = product
            mock_filter.return_value.update.return_value = 0
            with self.assertRaises(ConcurrentUpdateError):
                adjust_stock(self.product.id, 1)


class ProductDetailApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.product = Product.objects.create(
            name='API Widget',
            description='Detail',
            price=Decimal('12.00'),
            stock=3,
        )

    def test_product_detail_endpoint(self):
        response = self.client.get(f'/api/products/{self.product.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'API Widget')
