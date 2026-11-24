"""Minimal Django settings for the last-seat reservation exercise."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Test-only value; real deployments must supply DJANGO_SECRET_KEY from the environment.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "task05-tests-only-not-a-secret")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = ["reservations"]

# Empty POSTGRES_PORT/POSTGRES_PASSWORD are passed through as-is for the unix-socket fallback.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "task05",
        "USER": os.environ.get("POSTGRES_USER", "assessment"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
