from django.test import TransactionTestCase
from django.contrib.auth.models import User
import time
from django.db import connection
from helper.performance_report import PerformanceTestMixin, PerformanceReport

class AccountsPerformanceTests(PerformanceTestMixin, TransactionTestCase):
    
    def test_bulk_user_creation_performance(self):
        """
        مراقبة أداء قاعدة البيانات عند ضغط إدخال بيانات ضخمة (Bulk Inserts).
        تسجيل ١٠٠٠ مستخدم في عملية واحدة وحساب الزمن الفعلي للحفظ.
        """
        start_time = time.time()
        initial_queries = len(connection.queries)
        
        users = [
            User(username=f"user_{i}", email=f"user_{i}@test.com")
            for i in range(1000)
        ]
        
        # استخدام bulk_create لتقليل النفقات والمحافظة على الأداء
        User.objects.bulk_create(users)
        
        end_time = time.time()
        final_queries = len(connection.queries)
        
        execution_time = end_time - start_time
        queries_made = final_queries - initial_queries
        
        print(f"\n[Performance] 1000 Users inserted in {execution_time:.4f}s with {queries_made} DB Query.")
        PerformanceReport.instance().record_metric(
            name=self.id(),
            metric="bulk_insert",
            value=1000,
            unit="rows",
            extra={"duration_s": execution_time, "queries": queries_made},
        )
        
        self.assertLess(execution_time, 5.0, "عملية إنشاء الحسابات استغرقت وقتاً أطول من المتوقع")
