from decouple import config
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost').split(',')
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='').split(',') if config('CSRF_TRUSTED_ORIGINS', default='') else []

DJANGO_APPS = [
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'unfold.contrib.inlines',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
]

THIRD_PARTY_APPS = [
    'django_celery_beat',
    'rest_framework',
    'rest_framework.authtoken',
    'encrypted_model_fields',  # I1: PDPA field-level encryption
]

LOCAL_APPS = [
    'apps.core',
    'apps.billing',
    'apps.rooms',
    'apps.tenants',
    'apps.maintenance',
    'apps.notifications',
    'apps.dashboard',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'config.middleware.ActiveDormitoryMiddleware',
    'config.middleware.ForcePasswordChangeMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='dms'),
        'USER': config('DB_USER', default='dms'),
        'PASSWORD': config('DB_PASSWORD', default='dms'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

import sys
if 'test' in sys.argv:
    # I8: ใช้ PostgreSQL แยกสำหรับ test เพื่อให้ select_for_update() และ JSON queries
    # ทำงานเหมือน production — SQLite รองรับ behavior เหล่านี้ต่างกัน
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('TEST_DB_NAME', default='dms_test'),
        'USER': config('DB_USER', default='dms'),
        'PASSWORD': config('DB_PASSWORD', default='dms'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'TEST': {
            'NAME': config('TEST_DB_NAME', default='dms_test'),
        },
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'core.CustomUser'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

LOCALE_PATHS = [BASE_DIR / 'locale']

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = config('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

LINE_CHANNEL_ACCESS_TOKEN = config('LINE_CHANNEL_ACCESS_TOKEN', default='')
LINE_CHANNEL_SECRET = config('LINE_CHANNEL_SECRET', default='')
TMR_WEBHOOK_SECRET = config('TMR_WEBHOOK_SECRET', default='')

# I1: PDPA — Field-level encryption key สำหรับ EncryptedCharField
# ต้องตั้งค่าใน .env ก่อน deploy production
# สร้างด้วย: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='')

# ---------------------------------------------------------------------------
# B4: Production Security Settings
# ควบคุมด้วย PRODUCTION=True ใน .env — ไม่บังคับใช้ใน local dev
# ---------------------------------------------------------------------------
PRODUCTION = config('PRODUCTION', default=False, cast=bool)

if PRODUCTION:
    # บังคับ HTTPS สำหรับทุก request
    SECURE_SSL_REDIRECT = True
    # HSTS: บอก browser ให้ใช้ HTTPS อย่างน้อย 1 ปี (31536000 วินาที)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Cookie security — ป้องกัน cookie ถูก steal ผ่าน HTTP หรือ JS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # ป้องกัน browser ตีความ content-type ผิด (MIME sniffing attack)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # ป้องกัน XSS ผ่าน browser built-in filter (legacy browsers)
    SECURE_BROWSER_XSS_FILTER = True
    # ป้องกัน clickjacking
    X_FRAME_OPTIONS = 'DENY'

# ---------------------------------------------------------------------------
# B7: Logging Configuration
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': config('LOG_FILE', default=str(BASE_DIR / 'logs' / 'dms.log')),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': config('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
        # Log billing และ webhook events แยกไว้ตรวจสอบย้อนหลังได้
        'apps.billing': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'apps.notifications': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# สร้าง logs directory ถ้ายังไม่มี
import os
LOG_DIR = BASE_DIR / 'logs'
os.makedirs(LOG_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# B7: Sentry Error Tracking
# ตั้ง SENTRY_DSN ใน .env เพื่อเปิดใช้งาน — ถ้าไม่มีค่าจะ skip ไป
# ---------------------------------------------------------------------------
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        # ส่ง performance traces 10% ใน production — ปรับได้ตามต้องการ
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        # แนบ release version เพื่อ track regression
        release=config('APP_VERSION', default='unknown'),
        environment='production' if PRODUCTION else 'development',
    )

# Django REST Framework — ใช้ Token authentication + pagination มาตรฐาน
# Rate limit: 100 requests/day per user เพื่อป้องกัน API abuse
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.TokenAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '100/day',
    },
}

# Override settings สำหรับ test — ต้องอยู่หลัง CACHES และ REST_FRAMEWORK
if 'test' in sys.argv:
    # ใช้ LocMemCache ในเทสเพื่อหลีกเลี่ยง Redis dependency (throttle + cache)
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    # ปิด throttling ในเทสเพื่อไม่ให้รบกวน API tests
    REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []
