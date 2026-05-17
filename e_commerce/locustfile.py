from locust import HttpUser, task, between
import random
import secrets  # أداة آمنة لتوليد النصوص العشوائية


class UserTask(HttpUser):
    wait_time = between(0.1, 0.5)
    cart_has_items = False
    
    def on_start(self):
        """تسجيل الدخول عند البدء"""
        random_id = random.randint(10000, 99999)
        self.username = f"locust_user_{random_id}"
        password = secrets.token_urlsafe(12) + "A1!"
        
        # 1. التسجيل
        self.client.post("/api/accounts/signup/", json={
            "username": self.username,
            "email": f"{self.username}@example.com",
            "password": password
        }, name="Signup User")
        
        # 2. تسجيل الدخول
        response = self.client.post("/api/accounts/login/", json={
            "username": self.username,
            "password": password
        }, name="Login User")
        
        if response.status_code == 200:
            self.token = response.json()['token']
        else:
            print(f"فشل تسجيل الدخول لـ {self.username}")
            self.token = None

    @task(3)
    def view_products(self):
        """عرض المنتجات"""
        if self.token:
            headers = {"Authorization": f"Token {self.token}"}
            self.client.get("/api/products/", headers=headers, name="View Products")

    def get_random_available_product(self):
        """جلب منتج عشوائي من القائمة"""
        headers = {"Authorization": f"Token {self.token}"}
        response = self.client.get("/api/products/", headers=headers, name="Get Product List")
        
        if response.status_code == 200:
            products = response.json()
            if products:
                return random.choice(products)['id']
        return None

    @task(5)
    def add_to_cart(self):
        """إضافة للسلة"""
        if self.token:
            product_id = self.get_random_available_product()
            print(f"محاولة إضافة المنتج {product_id} للسلة")
            if product_id:
                headers = {"Authorization": f"Token {self.token}"}
                response = self.client.post("/api/cart/create/", json={
                    "products_id": product_id,
                    "quantity": 1
                }, headers=headers, name="Add to Cart")
                
                if response.status_code == 201:
                    self.cart_has_items = True
                else:
                    print(f"فشل إضافة للسلة: {response.status_code}")
            else:
                print("⚠️ لا توجد منتجات متاحة")

    @task(2)
    def create_invoice(self):
        """إنشاء الفاتورة"""
        if self.token:
            if self.cart_has_items:
                headers = {"Authorization": f"Token {self.token}"}
                self.client.post("/api/invoices/create/", headers=headers, name="Create Order Invoice")
                self.cart_has_items = False
            else:
                # إضافة منتج وإنشاء الفاتورة
                product_id = self.get_random_available_product()
                if product_id:
                    headers = {"Authorization": f"Token {self.token}"}
                    self.client.post("/api/cart/create/", json={
                        "products_id": product_id, 
                        "quantity": 1
                    }, headers=headers, name="Add to Cart (Fix)")
                    self.client.post("/api/invoices/create/", headers=headers, name="Create Order Invoice")
                    self.cart_has_items = False

    @task
    def view_wallet(self):
        """عرض المحفظة"""
        if self.token:
            headers = {"Authorization": f"Token {self.token}"}
            self.client.get("/api/wallets/my-wallet/", headers=headers, name="View Wallet")

    @task
    def add_balance_wallet(self):
        """شحن المحفظة"""
        if self.token:
            headers = {"Authorization": f"Token {self.token}"}
            self.client.patch(
                "/api/wallets/add-funds/", 
                headers=headers, 
                name="Add Funds to Wallet",
                json={"amount": "100"}
            )