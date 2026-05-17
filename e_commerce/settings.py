
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent



SECRET_KEY = os.environ.get('SECRET_KEY')

DEBUG = True

ALLOWED_HOSTS = [ '127.0.0.1','localhost']



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
     'silk',
    'django_psutil_dash',

]





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
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',   # للزوار المجهولين
        'rest_framework.throttling.UserRateThrottle',   # للمستخدمين المسجلين
        'rest_framework.throttling.ScopedRateThrottle', # لكل endpoint على حدة
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/minute',      # ← 20 طلب/دقيقة للزوار
        'user': '100/minute',     # ← 100 طلب/دقيقة للمستخدم العادي
        'create-order': '10/minute',  # ← 10 طلبات/دقيقة لإنشاء الفاتورة (حماية الشراء)
        'wallet-add': '3/minute',    # ← 3 طلبات/دقيقة لإضافة رصيد
    }
}

MIDDLEWARE = [
     'silk.middleware.SilkyMiddleware',
    'drf_api_logger.middleware.api_logger_middleware.APILoggerMiddleware', # يفضل وضعه في البداية
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
        'CONN_MAX_AGE': 0,
        
        # ═══════════════════════════════════════════════
        # 🏊 إعدادات تجمع الاتصالات (Pool)
        # ═══════════════════════════════════════════════
        'POOL_OPTIONS': {
            'POOL_SIZE': 10,           # ← 10 اتصالات دائمة
            'MAX_OVERFLOW': 5,         # ← 5 اتصالات إضافية في الذروة
            'RECYCLE': 3600,           # ← إعادة تدوير الاتصال كل ساعة
            'PRE_PING': True,          # ← التحقق من سلامة الاتصال قبل الاستخدام
            'POOL_TIMEOUT': 30,        # ← الانتظار 30 ثانية لاتصال حر
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

STATIC_URL = 'static/'

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

DRF_API_LOGGER_DATABASE = True
DRF_API_LOGGER_SKIP_URL_NAME = ['admin:', 'swagger', "docs",'redoc']
DRF_API_LOGGER_QUEUE_MAX_SIZE = 50 
DRF_API_LOGGER_INTERVAL = 10   


SILKY_PYTHON_PROFILER = True           # ← تفعيل Python cProfile
SILKY_PYTHON_PROFILER_BINARY = True  # ← توليد ملفات .prof للتحليل العميق
SILKY_ANALYZE_QUERIES = True         # ← تحليل SQL queries
SILKY_META = True                    # ← عرض وقت Silk نفسه

# حماية الإنتاج: فقط الـ Staff يمكنهم رؤية /silk/
SILKY_AUTHENTICATION = True
SILKY_AUTHORISATION = True
SILKY_PERMISSIONS = lambda user: user.is_superuser

# تقليل التأثير على الأداء: تسجيل 10% فقط من الطلبات في الإنتاج
SILKY_RECORD_FRACTION = 0.1 if not DEBUG else 1.0

# حد حجم Request/Response (يمنع تضخم DB)
SILKY_MAX_REQUEST_BODY_SIZE = 1024   # 1KB
SILKY_MAX_RESPONSE_BODY_SIZE = 1024  # 1KB
