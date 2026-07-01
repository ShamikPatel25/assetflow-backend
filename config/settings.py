import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")


# Apps

SHARED_APPS = (
    "django_tenants",
    "apps.tenants",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    # "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "django_filters",

    # Public schema
    "apps.accounts",
)

TENANT_APPS = (
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    # "rest_framework_simplejwt.token_blacklist",

    # Tenant business apps
    "apps.employees",
    "apps.assets",
    "apps.allocations",
    "apps.requests",
    "apps.incidents",
    "apps.licenses",
    "apps.notifications",
    "apps.audit",
    "apps.search",
    "apps.ai",
)

INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

TENANT_MODEL = "tenants.Organization"
TENANT_DOMAIN_MODEL = "tenants.Domain"


# Middleware

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "apps.tenants.middleware.TenantRoutingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# URLs 

ROOT_URLCONF = "config.urls"
PUBLIC_SCHEMA_URLCONF = "config.urls_public"


# Templates

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database

DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)

DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": os.getenv("DATABASE_NAME"),
        "USER": os.getenv("DATABASE_USER"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD"),
        "HOST": os.getenv("DATABASE_HOST", "localhost"),
        "PORT": os.getenv("DATABASE_PORT", "5432"),
    }
}


# Auth

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend", # Default for public schema
    "apps.employees.custom_auth.TenantAuthBackend", # Custom for tenant schema
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static / Media

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# REST Framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.base.authentication.TenantJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.base.pagination.CustomPageNumberPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "apps.base.filters.BaseFilterBackend",
        "rest_framework.filters.SearchFilter",
        "apps.base.filters.CustomOrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}


# JWT

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("ACCESS_TOKEN_LIFETIME_MINUTES", 30))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("REFRESH_TOKEN_LIFETIME_DAYS", 7))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# CORS

if DEBUG:
    CORS_ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^http://[\w-]+\.localhost:3000$",
    ]
else:
    CORS_ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "x-csrftoken",
    "x-requested-with",
    "x-tenant",
]


# Logging

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}


# OpenAPI / Swagger

SPECTACULAR_SETTINGS = {
    "TITLE": "AssetFlow API",
    "DESCRIPTION": "Multi-Tenant Asset Management System API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "TAGS": [
        {"name": "Platform Auth", "description": "Super admin authentication"},
        {"name": "Organizations", "description": "Organization management"},
        {"name": "Tenant Auth", "description": "Tenant user authentication"},
        {"name": "Employees", "description": "Employee management"},
        {"name": "Departments", "description": "Department management"},
        {"name": "Assets", "description": "Asset inventory management"},
        {"name": "Allocations", "description": "Asset allocation management"},
        {"name": "Asset Requests", "description": "Asset request workflow"},
        {"name": "Incidents", "description": "Incident and repair management"},
        {"name": "Licenses", "description": "Software license management"},
        {"name": "Notifications", "description": "Notification management"},
        {"name": "Audit Logs", "description": "Audit trail"},
        {"name": "Dashboard", "description": "Dashboard analytics"},
    ],
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/",
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
        "filter": True,
    },
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "Bearer": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
    },
    "SECURITY": [{"Bearer": []}],
}


# Security (Production)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = "DENY"

# Email Configuration (Console for development)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@assetflow.local"
