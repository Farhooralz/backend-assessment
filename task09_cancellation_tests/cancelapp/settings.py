"""Minimal Django settings for the isolated cancellation-policy task."""

SECRET_KEY = "task09-tests-only-not-a-secret"  # noqa: S105
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = ["cancelapp"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
