"""Database bootstrap and shared fixtures for the goods-transfer API tests."""

import contextlib
import os

import psycopg
import pytest
from rest_framework.test import APIClient


def _connection(**overrides):
    """Connect to the maintenance database using the task environment contract."""
    params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "user": os.environ.get("POSTGRES_USER", "assessment"),
        "dbname": "postgres",
    }
    port = os.environ.get("POSTGRES_PORT", "5432")
    if port:
        params["port"] = int(port)
    password = os.environ.get("POSTGRES_PASSWORD", "")
    if password:
        params["password"] = password
    params.update(overrides)
    return psycopg.connect(**params)


def pytest_sessionstart(session):
    """Create the per-task database before pytest-django builds test_task04."""
    with (
        _connection(autocommit=True) as connection,
        connection.cursor() as cursor,
        contextlib.suppress(psycopg.errors.DuplicateDatabase),
    ):
        cursor.execute("CREATE DATABASE task04")


@pytest.fixture
def branch_a(db):
    from transfer.models import Branch

    return Branch.objects.create(name="A")


@pytest.fixture
def branch_b(db):
    from transfer.models import Branch

    return Branch.objects.create(name="B")


@pytest.fixture
def branch_c(db):
    from transfer.models import Branch

    return Branch.objects.create(name="C")


@pytest.fixture
def make_user(db):
    from django.contrib.auth import get_user_model

    from transfer.models import Staff

    def factory(username: str, branch, role: str):
        user = get_user_model().objects.create_user(username=username, password="test-password")
        Staff.objects.create(user=user, branch=branch, role=role)
        return user

    return factory


@pytest.fixture
def employee(branch_b, make_user):
    return make_user("employee", branch_b, "employee")


@pytest.fixture
def manager(branch_a, make_user):
    return make_user("manager", branch_a, "source_manager")


@pytest.fixture
def other_employee(branch_c, make_user):
    return make_user("other_employee", branch_c, "employee")


@pytest.fixture
def other_manager(branch_c, make_user):
    return make_user("other_manager", branch_c, "source_manager")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def draft(employee, branch_a, branch_b):
    from transfer.models import TransferRequest

    return TransferRequest.objects.create(
        source=branch_a,
        destination=branch_b,
        item_name="balls",
        quantity=3,
        created_by=employee,
    )


@pytest.fixture
def submitted(draft):
    from transfer.services import submit_request

    return submit_request(draft, draft.created_by)


@pytest.fixture
def no_profile_user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(username="noprofile", password="test-password")
