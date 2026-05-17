# استخدام صورة Python خفيفة
FROM python:3.11-slim

# تعيين متغيرات بيئية
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# إنشاء مجلد العمل أولاً لتنظيم النسخ
WORKDIR /app

# تثبيت نظام الحزم، تبعيات بايثون، وتنظيف المخلفات في خطوة واحدة
# تم إزالة musl-dev لأنه حزمة مخصصة لتوزيعات Alpine وليس Debian (slim)
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

# نسخ وتثبيت ملف المتطلبات (مرة واحدة فقط)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# حل مشكلة النسخ العشوائي: نسخ ملفات المشروع الأساسية فقط وتجنب الملفات الحساسة
COPY . /app

# إنشاء مجلد للملفات الثابتة وضبط الصلاحيات
RUN mkdir -p /app/staticfiles

# الأمر الافتراضي (يتم استبداله في docker-compose بـ gunicorn)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
