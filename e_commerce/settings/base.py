import os
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-production')

DEBUG = os.environ.get('DEBUG', 'True').lower() in ('1', 'true', 'yes')

ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    'nginx',
    'openresty',
    'openresty-rr',
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
    'app.common',
    'app.accounts',
    'app.product',
    'app.cart',
    'app.invoices',
    'app.wallets',
    'app.loadbalancing',
    'drf_spectacular',
    'drf_api_logger',
    'django_q',
]

CELERY_BEAT_SCHEDULE = {
    'weekly-report': {
        'task': 'app.invoices.tasks.generate_weekly_report',
        'schedule': crontab(hour=2, minute=0, day_of_week=1),
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'E-Commerce API',
    'DESCRIPTION': 'واجهة برمجة التطبيقات لمشروع التجارة الإلكترونية',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'app.common.exception_handler.api_exception_handler',
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'app.loadbalancing.middleware.ServedByMiddleware',
    'app.loadbalancing.middleware.RequestConcurrencyMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

PRODUCT_CACHE_TTL = int(os.getenv('PRODUCT_CACHE_TTL', '300'))

LB_NODE_ID = os.getenv('NODE_ID', 'local')
LB_SERVER_TIER = os.getenv('SERVER_TIER', 'MEDIUM')
LB_DEFAULT_COMPUTE_UNITS = 100
LB_MAX_COMPUTE_UNITS = 2048
LB_IGNORE_CLIENT_COMPUTE_HEADER = True
LB_REDIS_LIVE_STATE_TTL_SECONDS = 1
LB_SCRIPTS_DIR = BASE_DIR / 'scripts'
LB_SERVERS_CONFIG = LB_SCRIPTS_DIR / 'servers.django.json'
LB_ROUTING_CACHE_FILE = os.getenv('LB_ROUTING_CACHE_FILE', '/var/cache/routing/routing_cache.json')
LB_NODE_INFO = {
    'available_for_requests': True,
    'cpu_cores': float(os.getenv('LB_CPU_CORES', '4')),
    'cpu_clock_ghz': float(os.getenv('LB_CPU_CLOCK_GHZ', '2.8')),
    'ram_gb': float(os.getenv('LB_RAM_GB', '8')),
    'overhead_ms': float(os.getenv('LB_OVERHEAD_MS', '12')),
    'request_price': float(os.getenv('LB_REQUEST_PRICE', '0.025')),
}
LB_ROUTE_COMPUTE_UNITS = {
    '/api/products': 100,
    '/api/cart': 250,
    '/api/invoices/create': 900,
    '/api/wallets': 400,
}
