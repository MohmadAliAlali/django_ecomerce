from django.test import TransactionTestCase
from django.contrib.auth.models import User
from app.wallets.models import Wallet
import threading
from django.db import transaction, connection
from decimal import Decimal
from helper.performance_report import PerformanceTestMixin, PerformanceReport

class WalletConcurrencyTests(PerformanceTestMixin, TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create(username="testuser", password="password")
        # التأكد من وجود محفظة وإضافة رصيد لها 
        wallet, created = Wallet.objects.get_or_create(user=self.user)
        self.start_balance = Decimal('100.00')
        wallet.balance = self.start_balance
        wallet.save()

    def test_concurrent_wallet_deduction(self):
        """
        اختبار تنافس (Race Condition) عند محاولة خصم رصيد من المحفظة في نفس اللحظة.
        لدينا 100، ونقوم بـ 20 محاولة لخصم 10. يجب أن تنجح 10 محاولات فقط.
        """
        exceptions = []
        successful_deductions = []

        def deduct_balance(amount):
            try:
                with transaction.atomic():
                    # استخدام select_for_update يقفل الصف حتى تنتهي المعاملة (Transaction)
                    wallet = Wallet.objects.select_for_update().get(user=self.user)
                    if wallet.balance >= amount:
                        wallet.balance -= amount
                        wallet.save()
                        successful_deductions.append(True)
            except Exception as e:
                exceptions.append(e)
            finally:
                connection.close() # مهم لمنع قفل قاعدة البيانات بعد انتهاء ال Thread

        threads = []
        attempts = 20
        for _ in range(attempts):
            t = threading.Thread(target=deduct_balance, args=(Decimal('10.00'),))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.user.wallet.refresh_from_db()
        PerformanceReport.instance().record_concurrency(
            name=self.id(),
            attempts=attempts,
            successes=len(successful_deductions),
            errors=exceptions,
            expected_exact=10,
            note=f"start_balance={self.start_balance} final_balance={self.user.wallet.balance}",
        )
        self.assertEqual(len(successful_deductions), 10, "يجب أن تنجح 10 عمليات خصم فقط لتستنفد ال 100")
        self.assertEqual(self.user.wallet.balance, Decimal('0.00'), "الرصيد النهائي يجب أن يكون 0")
        self.assertEqual(exceptions, [])
