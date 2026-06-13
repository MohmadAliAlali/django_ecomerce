from django.test import RequestFactory, SimpleTestCase, override_settings
from django.http import HttpResponse
from rest_framework.test import APIClient

from app.loadbalancing.middleware import ServedByMiddleware
from app.loadbalancing.route_compute import resolve_compute_units


@override_settings(LB_NODE_ID='test-node')
class LoadBalancingMiddlewareTests(SimpleTestCase):
    def test_served_by_header(self):
        factory = RequestFactory()
        request = factory.get('/api/products/1/')
        middleware = ServedByMiddleware(lambda req: HttpResponse('ok'))

        with override_settings(NODE_ID='test-node'):
            response = middleware(request)
        self.assertEqual(response['X-Served-By'], 'test-node')

    def test_compute_units_for_products(self):
        units = resolve_compute_units('/api/products/1/')
        self.assertEqual(units, 100)


@override_settings(LB_NODE_ID='test-node', NODE_ID='test-node')
class NodeInfoViewTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_node_info_endpoint(self):
        response = self.client.get('/internal/node-info')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['nodeId'], 'test-node')
        self.assertIn('activeRequests', response.data)
        self.assertIn('inFlightComputeUnits', response.data)


class LoadDistributionViewTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_route_requires_compute_units(self):
        response = self.client.post('/api/load-distribution/route', {}, format='json')
        self.assertEqual(response.status_code, 400)
