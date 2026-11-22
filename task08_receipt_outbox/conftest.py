"""Test environment: real PostgreSQL/Redis from ../.env, eager Celery, isolated fake."""

import pytest

from db_utils import ensure_database


@pytest.fixture(scope="session")
def task08_database() -> None:
    """Create the task database before pytest-django creates test_task08."""
    ensure_database()


@pytest.fixture(autouse=True)
def _test_environment(task08_database: None, db: None, settings: object) -> None:
    """Run Celery inline and reset the Fake service for every test."""
    from celery_app import app
    from receipts import fake_service

    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    app.config_from_object("django.conf:settings", namespace="CELERY", force=True)
    fake_service.set_fake_mode("ok")
