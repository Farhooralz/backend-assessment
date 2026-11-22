"""Django settings for the standalone receipt-outbox assessment task."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "task08-local-only-not-a-secret")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = ["receipts"]
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "task08",
        "USER": os.environ.get("POSTGRES_USER", "assessment"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

_REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
_REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
CELERY_BROKER_URL = f"redis://{_REDIS_HOST}:{_REDIS_PORT}/8"
CELERY_RESULT_BACKEND = f"redis://{_REDIS_HOST}:{_REDIS_PORT}/8"
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BEAT_SCHEDULE = {
    "sweep-pending-receipts": {
        "task": "receipts.tasks.sweep_outbox",
        "schedule": 5.0,
    },
}
