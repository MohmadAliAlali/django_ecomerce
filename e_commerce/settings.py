
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent



SECRET_KEY = os.environ.get('SECRET_KEY')

DEBUG = True

ALLOWED_HOSTS = [
     '127.0.0.1',
     'localhost', 
     'nginx',           # ← Add this
     'app_main',
     'app_worker_1',
     'app_worker_2',
     '*', 
]



DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework.authtoken', 
    'rest_framework',   
    'app.accounts',
    'app.product',
    'app.cart',
    'app.invoices',
    'app.wallets',
    'drf_spectacular',
    'drf_api_logger',
    'django_q',
    #  'silk',
    # 'django_psutil_dash',

]

# Q_CLUSTER = {
#     'name': 'DjangoORM',
#     'workers': 4,
#     'recycle': 500,
#     'timeout': 90,
#     'retry': 120,
#     'queue_limit': 50,
#     'bulk': 10,
#     'orm': 'default',
#     'redis': {
#         'host': os.getenv('REDIS_HOST', 'redis'),  # ← redis وليس localhost
#         'port': 6379,
#         'db': 0,
#     }
# }



SPECTACULAR_SETTINGS = {
    'TITLE': 'E-Commerce API',
    'DESCRIPTION': 'واجهة برمجة التطبيقات لمشروع التجارة الإلكترونية',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',  # <--- الأولوية للتوكن
        'rest_framework.authentication.SessionAuthentication', # الإبقاء عليه للمتصفح
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # ═══════════════════════════════════════════════
    # 🛡️ إدارة الموارد: Throttling
    # ═══════════════════════════════════════════════
    # 'DEFAULT_THROTTLE_CLASSES': [
    #     'rest_framework.throttling.AnonRateThrottle',   # للزوار المجهولين
    #     'rest_framework.throttling.UserRateThrottle',   # للمستخدمين المسجلين
    #     'rest_framework.throttling.ScopedRateThrottle', # لكل endpoint على حدة
    # ],
    # 'DEFAULT_THROTTLE_RATES': {
    #     'anon': '20/minute',      # ← 20 طلب/دقيقة للزوار
    #     'user': '1000/minute',     # ← 1000 طلب/دقيقة للمستخدم العادي
    #     'create-order': '30/minute',  # ← 30 طلبات/دقيقة لإنشاء الفاتورة (حماية الشراء)
    #     'wallet-add': '3/minute',    # ← 3 طلبات/دقيقة لإضافة رصيد
    # }
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 'helper.performance.PerformanceTrackingMiddleware',
]

ROOT_URLCONF = 'e_commerce.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'e_commerce.wsgi.application'

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        # الاعتماد الكامل على المتغيرات البيئية بدون وضع كلمات مرور افتراضية نصية
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'db'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 60,
        
        # ═══════════════════════════════════════════════
        # 🏊 إعدادات تجمع الاتصالات (Pool)
        # ═══════════════════════════════════════════════
        'POOL_OPTIONS': {
            'POOL_SIZE': 10,           # ← 10 اتصالات دائمة
            'MAX_OVERFLOW': 20,         # ← 20 اتصالات إضافية في الذروة
            'RECYCLE': 3600,           # ← إعادة تدوير الاتصال كل ساعة
            'PRE_PING': True,          # ← التحقق من سلامة الاتصال قبل الاستخدام
            'POOL_TIMEOUT': 60,        # ← الانتظار 60 ثانية لاتصال حر
        },
    }
}



AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')  # ← هذا المفقود

# (اختياري) إذا كان لديك مجلدات static إضافية
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"


CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']

CELERY_TASK_SERIALIZER = 'json'

CELERY_RESULT_SERIALIZER = 'json'
