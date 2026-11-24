"""Celery application: Redis is the broker, PostgreSQL holds durable state."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "task08_settings")

app = Celery("task08")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["receipts"])
