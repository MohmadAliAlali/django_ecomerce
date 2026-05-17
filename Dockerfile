# استخدام صورة Python خفيفة
FROM python:3.11-slim

# تعيين متغيرات بيئية
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# تثبيت نظام الحزم والتبعيات
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client gcc python3-dev musl-dev \
    && rm -rf /var/lib/apt/lists/*

# إنشاء مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات وتثبيتها
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي المشروع
COPY . /app

# إنشاء مجلد للملفات الثابتة
RUN mkdir -p /app/staticfiles

# الأمر الافتراضي (يتم استبداله في docker-compose بـ gunicorn)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]