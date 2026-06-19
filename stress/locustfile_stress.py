"""
Stress test Locust profile (course requirement #9).

Simulates 100+ concurrent users: health checks, catalog reads, cart, checkout.
Run via scripts/run_stress_test.py or headless:

  locust -f stress/locustfile_stress.py --host=http://openresty:80 \\
    --headless -u 100 -r 10 --run-time 120s
"""

from locust import HttpUser, task, between
import random
import secrets


class StressUser(HttpUser):
    wait_time = between(0.3, 1.5)
    cart_has_items = False

    def on_start(self):
        random_id = random.randint(100000, 999999)
        self.username = f"stress_{random_id}"
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
                json={"amount": "1000.00"},
                headers=headers,
                name="Seed Wallet Funds",
            )
        else:
            self.token = None

    def _headers(self):
        return {"Authorization": f"Token {self.token}"}

    @task(2)
    def health(self):
        self.client.get("/api/health/", name="Health Check")

    @task(5)
    def view_products(self):
        if not self.token:
            return
        self.client.get("/api/products/", headers=self._headers(), name="View Products")

    @task(3)
    def product_detail(self):
        if not self.token:
            return
        response = self.client.get("/api/products/", headers=self._headers(), name="Get Product List")
        if response.status_code != 200:
            return
        products = response.json()
        if not products:
            return
        product_id = random.choice(products)["id"]
        self.client.get(
            f"/api/products/{product_id}/",
            headers=self._headers(),
            name="Product Detail",
        )

    @task(4)
    def add_to_cart(self):
        if not self.token:
            return
        response = self.client.get("/api/products/", headers=self._headers(), name="Get Product List")
        if response.status_code != 200:
            return
        products = response.json()
        if not products:
            return
        product_id = random.choice(products)["id"]
        response = self.client.post(
            "/api/cart/create/",
            json={"products_id": product_id, "quantity": 1},
            headers=self._headers(),
            name="Add to Cart",
        )
        if response.status_code == 201:
            self.cart_has_items = True

    @task(3)
    def checkout(self):
        if not self.token:
            return
        headers = self._headers()
        if not self.cart_has_items:
            response = self.client.get("/api/products/", headers=headers, name="Get Product List")
            if response.status_code != 200:
                return
            products = response.json()
            if not products:
                return
            product_id = random.choice(products)["id"]
            self.client.post(
                "/api/cart/create/",
                json={"products_id": product_id, "quantity": 1},
                headers=headers,
                name="Add to Cart (Fix)",
            )
        self.client.post("/api/invoices/create/", headers=headers, name="Create Order Invoice")
        self.cart_has_items = False

    @task(1)
    def view_wallet(self):
        if not self.token:
            return
        self.client.get("/api/wallets/my-wallet/", headers=self._headers(), name="View Wallet")
