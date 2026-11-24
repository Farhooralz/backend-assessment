"""Minimal Django settings for the branch-invoice JWT task."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _required_secret(name: str) -> str:
    """Fail closed: a missing key must stop startup, never silently weaken signing."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in the environment")
    return value


SECRET_KEY = _required_secret("DJANGO_SECRET_KEY")
JWT_SECRET_KEY = _required_secret("JWT_SECRET_KEY")
if len(JWT_SECRET_KEY.encode("utf-8")) < 32:
    raise ImproperlyConfigured("JWT_SECRET_KEY must be at least 32 bytes")
JWT_ALGORITHM = "HS256"

DEBUG = False
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "drf_spectacular",
    "access",
]

MIDDLEWARE: list[str] = []

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

ROOT_URLCONF = "jwtbranch.urls"
WSGI_APPLICATION = "jwtbranch.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "task06",
        "USER": os.environ.get("POSTGRES_USER", "assessment"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS: list[dict] = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379") or "6379")
REDIS_DB = 6  # task-isolated database index, per the shared-infrastructure contract
LOGIN_FAILURE_WINDOW_SECONDS = 60
LOGIN_FAILURE_LIMIT = 5  # five failures are tolerated; the 6th in the window is rejected

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["access.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
}

# The docs views keep drf-spectacular's public defaults; every API view keeps the
# REST_FRAMEWORK defaults above. Authentication is left on the docs view solely so
# the Swagger UI shows the Bearer "Authorize" button.
SPECTACULAR_SETTINGS = {
    "TITLE": "Branch invoice API",
    "DESCRIPTION": "JWT-authenticated, branch-scoped invoice access.",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_PUBLIC": False,
}
