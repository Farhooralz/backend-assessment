"""Minimal Django settings for the isolated cancellation-policy task."""

import os

SECRET_KEY = "task09-tests-only-not-a-secret"  # noqa: S105
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = ["cancelapp"]

# Real PostgreSQL is required: the concurrency test relies on SELECT FOR UPDATE.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "task09",
        "USER": os.environ.get("POSTGRES_USER", "assessment"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
