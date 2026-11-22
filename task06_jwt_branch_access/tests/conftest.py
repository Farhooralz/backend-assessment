"""Shared fixtures for the branch-invoice API tests."""

import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
import redis
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from access.models import Branch, Invoice, Membership

LOGIN_URL = "/api/token/"
REFRESH_URL = "/api/token/refresh/"
LOGOUT_URL = "/api/token/logout/"
INVOICES_URL = "/api/invoices/"


@pytest.fixture(autouse=True)
def clean_login_counters() -> object:
    """DB state rolls back per test; Redis does not, so reset the throttle keys."""
    client = redis.Redis(
        host=os.environ.get("REDIS_HOST", settings.REDIS_HOST),
        port=int(os.environ.get("REDIS_PORT", settings.REDIS_PORT) or "6379"),
        db=settings.REDIS_DB,
    )
    client.flushdb()
    yield client
    client.flushdb()


def login(api: APIClient, username: str = "analyst", password: str = "pw") -> dict:
    """Log in through the real endpoint and return the token pair."""
    response = api.post(LOGIN_URL, {"username": username, "password": password}, format="json")
    assert response.status_code == 200, response.data
    return response.data


def auth(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def branch_a(db) -> Branch:
    return Branch.objects.create(name="A")


@pytest.fixture
def branch_b(db) -> Branch:
    return Branch.objects.create(name="B")


@pytest.fixture
def analyst(db, branch_a, branch_b):
    user = get_user_model().objects.create_user(username="analyst", password="pw")
    Membership.objects.create(user=user, branch=branch_a, role=Membership.ROLE_ANALYST)
    Membership.objects.create(user=user, branch=branch_b, role=Membership.ROLE_ANALYST)
    return user


@pytest.fixture
def customer(db, branch_a):
    user = get_user_model().objects.create_user(username="customer", password="pw")
    Membership.objects.create(user=user, branch=branch_a, role=Membership.ROLE_CUSTOMER)
    return user


@pytest.fixture
def invoices(db, branch_a, branch_b, analyst, customer) -> SimpleNamespace:
    outside = Branch.objects.create(name="outside")
    return SimpleNamespace(
        a=Invoice.objects.create(branch=branch_a, number="A-1", amount=Decimal("100.00")),
        b=Invoice.objects.create(branch=branch_b, number="B-1", amount=Decimal("200.00")),
        outside=Invoice.objects.create(branch=outside, number="X-1", amount=Decimal("999.00")),
        own=Invoice.objects.create(
            branch=outside, customer=customer, number="OWN-1", amount=Decimal("50.00")
        ),
    )
