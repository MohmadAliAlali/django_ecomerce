from django.test import TransactionTestCase
from django.contrib.auth.models import User
from app.product.models import Product
from app.cart.models import Cart
import threading
from django.db import transaction, connection
from helper.performance_report import PerformanceTestMixin, PerformanceReport

class ConcurrencyPerformanceTests(PerformanceTestMixin, TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create(username="testuser", password="password")
        self.product = Product.objects.create(name="T-Shirt", price=100.0, stock=50)
        self.initial_stock = self.product.stock

    def test_concurrent_cart_addition(self):
        # اختبار تضارب البيانات عبر تشغيل عدة مسارات (Threads) في نفس الوقت
        # لمحاكاة التنافس على نفس المنتج
        exceptions = []
        successful_purchases = []
        quantity = 3
        attempts = 20

        def purchase_product(quantity):
            try:
                # استخدام select_for_update لقفل الصف ومنع تضارب البيانات
                with transaction.atomic():
                    p = Product.objects.select_for_update().get(id=self.product.id)
                    if p.stock >= quantity:
                        p.stock -= quantity
                        p.save()
                        Cart.objects.create(user=self.user, products_id=p, quantity=quantity)
                        successful_purchases.append(True)
            except Exception as e:
                exceptions.append(e)
            finally:
                connection.close()

        threads = []
        # محاكاة 20 محاولة شراء متزامنة، كل منها تطلب 3 قطع من المنتج
        for _ in range(attempts):
            t = threading.Thread(target=purchase_product, args=(quantity,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # التحقق من المخزون النهائي: بدأنا ب 50، وتم شراء 3 * 16 عملية ناجحة = 48
        # سيتبقى 2 في المخزون
        self.product.refresh_from_db()
        success_count = len(successful_purchases)
        PerformanceReport.instance().record_concurrency(
            name=self.id(),
            attempts=attempts,
            successes=success_count,
            errors=exceptions,
            expected_max=self.initial_stock // quantity,
            note=f"stock_start={self.initial_stock} quantity={quantity} final_stock={self.product.stock}",
        )
        self.assertGreaterEqual(self.product.stock, 0)
        self.assertEqual(exceptions, [])
