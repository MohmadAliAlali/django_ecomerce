# مشروع E-Commerce (Django + DRF + PostgreSQL + Redis + Celery)

هذا الملف يشرح طريقة تنصيب وتشغيل المشروع، تشغيل الخدمات التابعة له، وكيفية الوصول إلى واجهات الـ API.

## 1) المتطلبات

- Docker و Docker Compose
- أو (اختياري) Python 3.11 و PostgreSQL و Redis للتشغيل المحلي بدون Docker

## 2) تشغيل المشروع باستخدام Docker (الطريقة الموصى بها)

من جذر المشروع شغّل:

```bash
docker compose up --build
```

بعد التشغيل ستكون الخدمات كالتالي:

- `web` (Django API): على المنفذ `8000`
- `db` (PostgreSQL): على المنفذ `5432`
- `redis`: على المنفذ `6379`
- `celery` (عامل المهام الخلفية): يعمل في الخلفية داخل Docker Compose

رابط التطبيق:

- `http://localhost:8000`

### تشغيل Locust (اختبار التحمل)

خدمة `locust` مفعّلة عبر profile باسم `loadtest`:

```bash
docker compose --profile loadtest up --build locust
```

واجهة Locust:

- `http://localhost:8089`

## 3) إيقاف الخدمات

```bash
docker compose down
```

لحذف الفوليوم (قاعدة البيانات) أيضًا:

```bash
docker compose down -v
```

## 4) التشغيل المحلي بدون Docker (اختياري)

> هذا الخيار مفيد أثناء التطوير إذا أردت تشغيل Django مباشرة.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

تأكد من إعداد متغيرات البيئة (خصوصًا إعدادات PostgreSQL و Redis)، ثم:

```bash
cd e_commerce
python manage.py migrate
python manage.py runserver
```

## 5) خدمات التوثيق التلقائي للـ API

بعد تشغيل المشروع:

- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- OpenAPI Schema: `http://localhost:8000/api/schema/`

## 6) المصادقة (Authentication)

المشروع يستخدم Token Authentication.

### إنشاء حساب

- `POST /api/accounts/signup/`

مثال Body:

```json
{
  "username": "user1",
  "email": "user1@example.com",
  "password": "StrongPass123"
}
```

### تسجيل الدخول

- `POST /api/accounts/login/`

مثال Body:

```json
{
  "username": "user1",
  "password": "StrongPass123"
}
```

الرد يتضمن `token`.

### استخدام التوكن

أضف الهيدر التالي في الطلبات المحمية:

```http
Authorization: Token <your_token>
```

## 7) مسارات الـ API المتوفرة

Base URL:

- `http://localhost:8000`

### Accounts

- `POST /api/accounts/signup/`
- `POST /api/accounts/login/`

### Products (متاحة بدون تسجيل دخول)

- `GET /api/products/` : قائمة المنتجات المتاحة
- `GET /api/products/<id>/` : تفاصيل منتج

### Cart (تحتاج توكن)

- `POST /api/cart/create/` : إضافة عنصر للسلة
- `GET /api/cart/my-cart/` : عرض سلة المستخدم
- `DELETE /api/cart/my-cart/delete/` : حذف السلة

مثال Body لإضافة عنصر:

```json
{
  "products_id": 1,
  "quantity": 2
}
```

### Wallets (تحتاج توكن)

- `GET /api/wallets/my-wallet/` : عرض الرصيد
- `PUT /api/wallets/add-funds/` : شحن الرصيد

مثال Body للشحن:

```json
{
  "amount": "100.00"
}
```

### Invoices (تحتاج توكن)

- `POST /api/invoices/create/` : إنشاء طلب شراء (غير متزامن عبر Celery)
- `GET /api/invoices/list/` : عرض الفواتير الخاصة بالمستخدم

## 8) أمثلة سريعة باستخدام curl

### تسجيل الدخول

```bash
curl -X POST http://localhost:8000/api/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"StrongPass123"}'
```

### عرض المنتجات

```bash
curl http://localhost:8000/api/products/
```

### إضافة منتج إلى السلة (مع توكن)

```bash
curl -X POST http://localhost:8000/api/cart/create/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token YOUR_TOKEN" \
  -d '{"products_id":1,"quantity":2}'
```

## 9) ملاحظات مهمة

- خدمة `web` تقوم تلقائيًا بتطبيق الـ migrations عند الإقلاع داخل Docker.
- تأكد أن خدمة `celery` تعمل إذا كنت ستستخدم إنشاء الطلبات (`/api/invoices/create/`) لأنه يعتمد على المهام الخلفية.
- واجهة الإدارة متاحة على:
  - `http://localhost:8000/admin/`
