"""Minimal Django settings for the branch-invoice JWT task."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Django's own secret and the JWT signing key are configuration, never source constants.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-django-key-change-in-production")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-only-jwt-key-change-in-production")
JWT_ALGORITHM = "HS256"

DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "access",
]

MIDDLEWARE: list[str] = []

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
LOGIN_FAILURE_LIMIT = 5  # the 6th failure in the window is rejected

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["access.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "UNAUTHENTICATED_USER": None,
}
