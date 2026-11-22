"""Test environment: real PostgreSQL/Redis from ../.env, eager Celery, isolated fake."""

import os

import psycopg
import pytest
from psycopg import sql

DB_NAME = "task08"


def _pg_params(dbname: str) -> dict[str, object]:
    """Build psycopg connection parameters from the shared environment contract."""
    port = os.environ.get("POSTGRES_PORT", "5432")
    return {
        "dbname": dbname,
        "user": os.environ.get("POSTGRES_USER", "assessment"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(port) if port else 5432,
    }


@pytest.fixture(scope="session")
def task08_database() -> None:
    """Create the task database before pytest-django creates test_task08."""
    with psycopg.connect(**_pg_params("postgres"), autocommit=True) as conn:
        found = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,)).fetchone()
        if not found:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))


@pytest.fixture(autouse=True)
def _test_environment(task08_database: None, db: None, settings: object) -> None:
    """Run Celery inline and reset the Fake service for every test."""
    from celery_app import app
    from receipts import fake_service

    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    app.config_from_object("django.conf:settings", namespace="CELERY", force=True)
    fake_service.set_fake_mode("ok")
