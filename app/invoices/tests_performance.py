from django.test import TransactionTestCase
from django.contrib.auth.models import User
from app.invoices.models import Invoice
import threading
from django.db import transaction, connection
from decimal import Decimal
from helper.performance_report import PerformanceTestMixin, PerformanceReport

class InvoiceConcurrencyTests(PerformanceTestMixin, TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create(username="testuser", password="password")
        self.invoice = Invoice.objects.create(
            user=self.user, 
            total_amount=Decimal('500.00'), 
            status='pending'
        )

    def test_concurrent_invoice_payment(self):
        """
        اختبار تنافس الدفع: المستخدم يحاول دفع الفاتورة من أكثر من جهاز في نفس اللحظة
        يجب أن يتم الدفع (تغيير الحالة) مرة واحدة فقط.
        """
        exceptions = []
        successful_payments = []

        def pay_invoice():
            try:
                with transaction.atomic():
                    inv = Invoice.objects.select_for_update().get(id=self.invoice.id)
                    if inv.status == 'pending':
                        # محاكاة الدفع أو خصم الرصيد
                        inv.status = 'access'
                        inv.save()
                        successful_payments.append(True)
            except Exception as e:
                exceptions.append(e)
            finally:
                connection.close()

        threads = []
        attempts = 10
        for _ in range(attempts):
            t = threading.Thread(target=pay_invoice)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.invoice.refresh_from_db()
        PerformanceReport.instance().record_concurrency(
            name=self.id(),
            attempts=attempts,
            successes=len(successful_payments),
            errors=exceptions,
            expected_exact=1,
            note=f"final_status={self.invoice.status}",
        )
        self.assertEqual(len(successful_payments), 1, "عملية الدفع يجب أن تتم مرة واحدة فقط")
        self.assertEqual(self.invoice.status, 'access')
        self.assertEqual(exceptions, [])
