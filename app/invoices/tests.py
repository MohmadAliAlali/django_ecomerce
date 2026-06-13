from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from app.cart.models import Cart
from app.product.models import Product
from app.wallets.models import Wallet


class PessimisticCheckoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='buyer', password='pass12345')
        self.other = User.objects.create_user(username='other', password='pass12345')
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        self.product = Product.objects.create(
            name='Last Unit',
            description='Only one left',
            price=Decimal('50.00'),
            stock=1,
        )
        Wallet.objects.filter(user=self.user).update(balance=Decimal('100.00'))
        Cart.objects.create(user=self.user, products_id=self.product, quantity=1)

    def test_checkout_debits_wallet_and_stock(self):
        response = self.client.post('/api/invoices/create/', {}, format='json')
        self.assertEqual(response.status_code, 201)

        self.product.refresh_from_db()
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(self.product.stock, 0)
        self.assertEqual(wallet.balance, Decimal('50.00'))
        self.assertFalse(Cart.objects.filter(user=self.user).exists())

    def test_checkout_fails_when_stock_insufficient(self):
        other_token = Token.objects.create(user=self.other)
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=f'Token {other_token.key}')
        Wallet.objects.filter(user=self.other).update(balance=Decimal('100.00'))
        Cart.objects.create(user=self.other, products_id=self.product, quantity=1)

        first = self.client.post('/api/invoices/create/', {}, format='json')
        second = other_client.post('/api/invoices/create/', {}, format='json')

        statuses = sorted([first.status_code, second.status_code])
        self.assertEqual(statuses, [201, 409])
