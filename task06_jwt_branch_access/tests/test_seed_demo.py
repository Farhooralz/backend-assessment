"""Round 3 contract: a repeatable demo seed that drives the documented walkthrough."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from access.models import Branch, Invoice, Membership

DEMO_ANALYST = "demo_analyst"
DEMO_CUSTOMER = "demo_customer"
PASSWORD = "walkthrough-pw-123"
LOGIN_URL = "/api/token/"
REFRESH_URL = "/api/token/refresh/"
LOGOUT_URL = "/api/token/logout/"
INVOICES_URL = "/api/invoices/"


def seed(**options: object) -> None:
    call_command("seed_demo", verbosity=0, **options)


@pytest.mark.django_db
def test_spec_seed_demo_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    seed()
    first = (
        Branch.objects.count(),
        get_user_model().objects.count(),
        Membership.objects.count(),
        Invoice.objects.count(),
    )
    seed()
    second = (
        Branch.objects.count(),
        get_user_model().objects.count(),
        Membership.objects.count(),
        Invoice.objects.count(),
    )
    assert second == first
    assert len(set(Invoice.objects.values_list("number", flat=True))) == Invoice.objects.count()


@pytest.mark.django_db
def test_spec_seed_demo_creates_analyst_in_two_branches_and_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    seed()
    analyst = get_user_model().objects.get(username=DEMO_ANALYST)
    customer = get_user_model().objects.get(username=DEMO_CUSTOMER)
    analyst_branches = set(
        Membership.objects.filter(
            user=analyst, role=Membership.ROLE_ANALYST, is_active=True
        ).values_list("branch__name", flat=True)
    )
    assert len(analyst_branches) == 2
    assert Membership.objects.filter(
        user=customer, role=Membership.ROLE_CUSTOMER, is_active=True
    ).exists()
    assert Invoice.objects.filter(
        number="DEMO-CUST-1", branch__name="Demo outside", customer=customer
    ).exists()


@pytest.mark.django_db
def test_spec_seed_demo_uses_env_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    seed()
    for username in (DEMO_ANALYST, DEMO_CUSTOMER):
        assert get_user_model().objects.get(username=username).check_password(PASSWORD)


@pytest.mark.django_db
def test_spec_seed_demo_generated_password_is_printed_once(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    seed()
    seed()
    printed = [
        line.split(":", 1)[1].strip()
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("demo password:")
    ]
    assert len(printed) == 1
    assert get_user_model().objects.get(username=DEMO_ANALYST).check_password(printed[0])


@pytest.mark.django_db
def test_spec_seed_demo_prints_demo_usernames(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    seed()
    output = capsys.readouterr().out
    assert DEMO_ANALYST in output
    assert DEMO_CUSTOMER in output
    assert PASSWORD not in output


@pytest.mark.django_db
def test_spec_seeded_demo_walkthrough_covers_login_scope_refresh_and_logout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    seed()
    api = APIClient()

    pair = api.post(LOGIN_URL, {"username": DEMO_ANALYST, "password": PASSWORD}, format="json")
    assert pair.status_code == 200
    access = pair.data["access"]
    refresh = pair.data["refresh"]
    response = api.get(INVOICES_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == 200
    assert {row["number"] for row in response.data} == {"DEMO-A-1", "DEMO-B-1"}

    # The customer's own invoice sits outside both analyst branches.
    outside = Invoice.objects.get(number="DEMO-CUST-1")
    assert (
        api.get(f"{INVOICES_URL}{outside.pk}/", HTTP_AUTHORIZATION=f"Bearer {access}").status_code
        == 404
    )
    customer_pair = api.post(
        LOGIN_URL, {"username": DEMO_CUSTOMER, "password": PASSWORD}, format="json"
    )
    assert customer_pair.status_code == 200
    owned = api.get(INVOICES_URL, HTTP_AUTHORIZATION=f"Bearer {customer_pair.data['access']}")
    assert [row["number"] for row in owned.data] == ["DEMO-CUST-1"]

    rotated = api.post(REFRESH_URL, {"refresh": refresh}, format="json")
    assert rotated.status_code == 200
    replay = api.post(REFRESH_URL, {"refresh": refresh}, format="json")
    assert replay.status_code == 401

    # Reuse detection revoked that whole session, so logout uses a fresh login.
    fresh = api.post(LOGIN_URL, {"username": DEMO_ANALYST, "password": PASSWORD}, format="json")
    assert fresh.status_code == 200
    logout = api.post(
        LOGOUT_URL, {}, HTTP_AUTHORIZATION=f"Bearer {fresh.data['access']}", format="json"
    )
    assert logout.status_code == 204
    assert (
        api.get(INVOICES_URL, HTTP_AUTHORIZATION=f"Bearer {fresh.data['access']}").status_code
        == 401
    )
