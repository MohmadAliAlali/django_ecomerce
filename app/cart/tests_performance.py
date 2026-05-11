from django.test import TransactionTestCase
from django.contrib.auth.models import User
from app.product.models import Product
from app.cart.models import Cart
import threading
from django.db import transaction, connection
from helper.performance_report import PerformanceTestMixin, PerformanceReport

class CartConcurrencyTests(PerformanceTestMixin, TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create(username="testuser", password="password")
        self.product = Product.objects.create(name="Laptop", price=1000.0, stock=10)

    def test_concurrent_update_cart_quantity(self):
        """
        اختبار التنافس على تحديث كمية منتج موجود بالفعل في السلة
        المنتج المخزون منه 10 فقط. وسنحاول زيادته 15 مرة بشكل متزامن.
        """
        cart_item = Cart.objects.create(user=self.user, products_id=self.product, quantity=1)
        attempts = 15
        initial_quantity = cart_item.quantity
        exceptions = []

        def increment_quantity():
            try:
                with transaction.atomic():
                    item = Cart.objects.select_for_update().get(id=cart_item.id)
                    # يجب أن لا تتخطى الكمية المطلوبة المخزون الفعلي
                    if item.quantity < self.product.stock:
                        item.quantity += 1
                        item.save()
            except Exception as e:
                exceptions.append(e)
            finally:
                connection.close()

        threads = []
        for _ in range(attempts): 
            t = threading.Thread(target=increment_quantity)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        cart_item.refresh_from_db()
        success_count = cart_item.quantity - initial_quantity
        PerformanceReport.instance().record_concurrency(
            name=self.id(),
            attempts=attempts,
            successes=success_count,
            errors=exceptions,
            expected_max=self.product.stock - initial_quantity,
            note=f"stock={self.product.stock} initial_qty={initial_quantity} final_qty={cart_item.quantity}",
        )
        self.assertLessEqual(cart_item.quantity, self.product.stock, "كمية السلة تجاوزت المخزون المتاح!")
        self.assertEqual(exceptions, [])
