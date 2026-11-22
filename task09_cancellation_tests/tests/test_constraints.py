"""A single deliverable check that pytest-django is configured against PostgreSQL."""

from django.conf import settings
from django.db import connection


def test_spec_uses_pytest_django(django_db_setup: None) -> None:
    assert settings.configured
    assert "cancelapp" in settings.INSTALLED_APPS
    assert connection.vendor == "postgresql"
