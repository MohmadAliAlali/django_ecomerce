"""Checkout-heavy Locust profile for demonstrating tier-aware load balancing."""

from locust import HttpUser, task, between
import random
import secrets


class CheckoutHeavyUser(HttpUser):
    wait_time = between(0.5, 1.5)
    cart_has_items = False

    def on_start(self):
        random_id = random.randint(100000, 999999)
        self.username = f"heavy_{random_id}"
        password = secrets.token_urlsafe(12) + "A1!"

        self.client.post(
            "/api/accounts/signup/",
            json={
                "username": self.username,
                "email": f"{self.username}@example.com",
                "password": password,
            },
            name="Signup User",
        )
        response = self.client.post(
            "/api/accounts/login/",
            json={"username": self.username, "password": password},
            name="Login User",
        )
        if response.status_code == 200:
            self.token = response.json()["token"]
            headers = {"Authorization": f"Token {self.token}"}
            self.client.put(
                "/api/wallets/add-funds/",
                json={"amount": "500.00"},
                headers=headers,
                name="Seed Wallet Funds",
            )
        else:
            self.token = None

    def _headers(self):
        return {"Authorization": f"Token {self.token}"}

    def _pick_product_id(self):
        response = self.client.get(
            "/api/products/",
            headers=self._headers(),
            name="Get Product List",
        )
        if response.status_code != 200:
            return None
        products = response.json()
        if not products:
            return None
        return random.choice(products)["id"]

    @task(1)
    def view_products(self):
        if not self.token:
            return
        self.client.get(
            "/api/products/",
            headers=self._headers(),
            name="View Products",
        )

    @task(4)
    def add_to_cart(self):
        if not self.token:
            return
        product_id = self._pick_product_id()
        if not product_id:
            return
        response = self.client.post(
            "/api/cart/create/",
            json={"products_id": product_id, "quantity": 1},
            headers=self._headers(),
            name="Add to Cart",
        )
        if response.status_code == 201:
            self.cart_has_items = True

    @task(12)
    def create_invoice(self):
        if not self.token:
            return
        headers = self._headers()
        if not self.cart_has_items:
            product_id = self._pick_product_id()
            if not product_id:
                return
            self.client.post(
                "/api/cart/create/",
                json={"products_id": product_id, "quantity": 1},
                headers=headers,
                name="Add to Cart (Fix)",
            )
        self.client.post(
            "/api/invoices/create/",
            headers=headers,
            name="Create Order Invoice",
        )
        self.cart_has_items = False
