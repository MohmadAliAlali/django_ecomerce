import random
from locust import HttpUser, task, between, SequentialTaskSet, events
from locust.exception import StopUser


class UserBehavior(SequentialTaskSet):
    """
    سيناريو حقيقي: يمثل رحلة مستخدم كامل من التسجيل حتى الشراء
    """

    def on_start(self):
        """تهيئة بيانات المستخدم الفريدة"""
        # استخدام عداد ثابت داخل الفئة لضمان الترتيب
        if not hasattr(UserBehavior, 'counter'):
            UserBehavior.counter = 0
        
        self.user_counter = UserBehavior.counter
        UserBehavior.counter += 1
        
        self.username = f"loaduser_{self.user_counter}_{random.randint(1000, 999999)}"
        self.email = f"{self.username}@test.com"
        self.password = "TestPass123!@#"
        self.token = None
        self.product_ids = []
        self.cart_items = []

    # ───────────────────────────────────────────────
    # الخطوة 1: التسجيل (Signup)
    # ───────────────────────────────────────────────
    @task
    def step_1_signup(self):
        payload = {
            "username": self.username,
            "email": self.email,
            "password": self.password,
            "password2": self.password
        }
        
        with self.client.post(
            "/api/accounts/signup/",
            json=payload,
            catch_response=True,
            name="01_Signup"
        ) as response:
            if response.status_code == 201:
                data = response.json()
                # التأكد من أن الرد يحتوي على التوكن
                self.token = data.get("key") or data.get("token") 
                response.success()
            elif response.status_code == 400:
                # إذا فشل التسجيل (مثلاً المستخدم موجود)، لا نستدعي تسجيل الدخول يدوياً.
                # نترك الخطأ يظهر في التقرير، وسينتقل الخطوة التالية (Login) تلقائياً
                response.failure(f"Signup validation error: {response.text}")
            else:
                response.failure(f"Signup failed: {response.status_code} - {response.text}")
                # لا نوقف المستخدم فوراً، ربما الخطأ مؤقت، نتركه يكمل المحاولة في الخطوة التالية

    # ───────────────────────────────────────────────
    # الخطوة 2: تسجيل الدخول (Login)
    # ───────────────────────────────────────────────
    @task
    def step_2_login(self):
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        # لا نرسل Authorization هنا لأننا لا نمتلك التوكن بعد
        with self.client.post(
            "/api/accounts/login/",
            json=payload,
            catch_response=True,
            name="02_Login"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                # DRF Token Auth يعيد عادة "key"
                self.token = data.get("key") or data.get("token")
                response.success()
            else:
                response.failure(f"Login failed: {response.status_code} - {response.text}")
                raise StopUser()

    # ───────────────────────────────────────────────
    # الخطوة 3: تصفح المنتجات (Browse Products)
    # ───────────────────────────────────────────────
    @task
    def step_3_browse_products(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        
        with self.client.get(
            "/api/products/",
            headers=headers,
            catch_response=True,
            name="03_List_Products"
        ) as response:
            if response.status_code == 200:
                try:
                    # التعامل مع Pagination القياسي في DRF (results)
                    data = response.json()
                    products = data.get("results") if isinstance(data, dict) else data
                    
                    if isinstance(products, list) and len(products) > 0:
                        self.product_ids = [p.get("id") for p in products if p.get("stock", 0) > 0]
                        response.success()
                    else:
                        response.failure("No products found or empty list")
                        raise StopUser()
                except ValueError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"Products list failed: {response.status_code}")

    @task
    def step_3b_view_product_details(self):
        if not self.product_ids:
            return
            
        product_id = random.choice(self.product_ids)
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        
        with self.client.get(
            f"/api/products/{product_id}/",
            headers=headers,
            catch_response=True,
            name="04_Product_Details"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Product details failed: {response.status_code}")

    # ───────────────────────────────────────────────
    # الخطوة 4: إدارة السلة (Cart Operations)
    # ───────────────────────────────────────────────
    @task
    def step_4_add_to_cart(self):
        if not self.product_ids:
            return
            
        selected_products = random.sample(self.product_ids, min(random.randint(1, 3), len(self.product_ids)))
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        
        for product_id in selected_products:
            quantity = random.randint(1, 3)
            # ملاحظة: تأكد أن "products_id" هو المفتاح الصحيح في Serializer الخاص بك
            payload = {
                "products_id": product_id, 
                "quantity": quantity
            }
            
            with self.client.post(
                "/api/cart/create/",
                json=payload,
                headers=headers,
                catch_response=True,
                name="05_Add_To_Cart"
            ) as response:
                if response.status_code in [201, 200]:
                    self.cart_items.append({"product_id": product_id, "quantity": quantity})
                    response.success()
                else:
                    # تسجيل الفشل دون إيقاف المستخدم
                    response.failure(f"Add to cart failed: {response.status_code} - {response.text}")

    @task
    def step_4b_view_cart(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        
        with self.client.get(
            "/api/cart/my-cart/",
            headers=headers,
            catch_response=True,
            name="06_View_Cart"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"View cart failed: {response.status_code}")

    # ───────────────────────────────────────────────
    # الخطوة 5: شحن المحفظة (Wallet Top-up)
    # ───────────────────────────────────────────────
    @task
    def step_5_check_wallet(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        
        with self.client.get(
            "/api/wallets/",
            headers=headers,
            catch_response=True,
            name="07_Check_Wallet"
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    # التعامل مع الحالة حيث تكون النتيجة قائمة أو قاموس
                    if isinstance(data, list) and len(data) > 0:
                        self.wallet_balance = float(data[0].get("balance", 0))
                    elif isinstance(data, dict):
                        self.wallet_balance = float(data.get("balance", 0))
                    response.success()
                except ValueError:
                    response.failure("Invalid JSON in wallet response")
            else:
                response.failure(f"Wallet check failed: {response.status_code}")

    @task
    def step_5b_add_funds(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        amount = round(random.uniform(100, 500), 2)
        
        # استخدام POST أو PATCH حسب تصميم الـ API الخاص بك
        # هنا افترضنا PATCH كما في كودك الأصلي
        with self.client.patch(
            "/api/wallets/add-funds/",
            json={"amount": amount},
            headers=headers,
            catch_response=True,
            name="08_Add_Funds"
        ) as response:
            if response.status_code == 200:
                self.wallet_balance += amount
                response.success()
            else:
                response.failure(f"Add funds failed: {response.status_code}")

    # ───────────────────────────────────────────────
    # الخطوة 6: إنشاء الفاتورة (Checkout/Invoice)
    # ───────────────────────────────────────────────
    @task
    def step_6_create_invoice(self):
        if not self.cart_items:
            return
            
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        
        with self.client.post(
            "/api/invoices/create/",
            json={},  # يعتمد على السلة في الخادم
            headers=headers,
            catch_response=True,
            name="09_Create_Invoice"
        ) as response:
            if response.status_code in [201, 200]:
                response.success()
            else:
                response.failure(f"Invoice creation failed: {response.status_code} - {response.text}")

    @task
    def step_6b_list_invoices(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        
        with self.client.get(
            "/api/invoices/list/",
            headers=headers,
            catch_response=True,
            name="10_List_Invoices"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Invoice list failed: {response.status_code}")

    # ───────────────────────────────────────────────
    # الخطوة 7: تسجيل الخروج / تنظيف
    # ───────────────────────────────────────────────
    @task
    def step_7_cleanup(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        
        with self.client.delete(
            "/api/cart/my-cart/delete/",
            headers=headers,
            catch_response=True,
            name="11_Delete_Cart"
        ) as response:
            if response.status_code in [204, 200, 404]:
                response.success()
            else:
                response.failure(f"Cart cleanup failed: {response.status_code}")

    def on_stop(self):
        pass


class WebsiteUser(HttpUser):
    """
    ملاحظة: تمت إزالة 'host' الثابت ليعتمد على الأمر --host عند التشغيل
    """
    tasks = [UserBehavior]
    wait_time = between(1, 5)

# ───────────────────────────────────────────────
# أحداث Locust
# ───────────────────────────────────────────────
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, 
               response, context, exception, **kwargs):
    if exception:
        print(f"❌ FAILED: {name} | {exception}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("🚀 بدء اختبار الحمل - سيناريو التجارة الإلكترونية الكامل")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("🏁 انتهى اختبار الحمل")