import time

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from app.common.performance_monitor import get_stats_snapshot, monitor_execution, reset_stats


class PerformanceMonitorTests(SimpleTestCase):
    def setUp(self):
        reset_stats()

    @override_settings(PERFORMANCE_MONITOR_ENABLED=True)
    def test_monitor_execution_records_stats(self):
        @monitor_execution('test.slow_fn')
        def slow_fn():
            time.sleep(0.002)
            return 42

        self.assertEqual(slow_fn(), 42)
        stats = get_stats_snapshot()
        self.assertIn('test.slow_fn', stats)
        self.assertEqual(stats['test.slow_fn']['count'], 1)
        self.assertGreaterEqual(stats['test.slow_fn']['mean_ms'], 0)

    @override_settings(PERFORMANCE_MONITOR_ENABLED=False)
    def test_monitor_disabled_skips_recording(self):
        @monitor_execution('test.disabled_fn')
        def fn():
            return 1

        fn()
        self.assertEqual(get_stats_snapshot(), {})


class HealthAndPerformanceApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_endpoint(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'UP')

    def test_performance_stats_reset(self):
        response = self.client.get('/api/performance/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), dict)

        reset = self.client.delete('/api/performance/stats/')
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()['reset'], True)
