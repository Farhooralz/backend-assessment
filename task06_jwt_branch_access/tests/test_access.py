"""List/detail scoping, live membership checks, IDOR and expired-token tests."""

from datetime import timedelta

import pytest

from access import tokens
from access.models import Membership
from tests.conftest import INVOICES_URL, auth, login


@pytest.mark.django_db
def test_spec_list_permission_scoped_by_membership(api, analyst, invoices) -> None:
    data = login(api)
    response = api.get(INVOICES_URL, **auth(data["access"]))
    assert response.status_code == 200
    assert {row["id"] for row in response.data} == {invoices.a.pk, invoices.b.pk}


@pytest.mark.django_db
def test_spec_detail_permission_allows_in_scope(api, analyst, invoices) -> None:
    data = login(api)
    response = api.get(f"{INVOICES_URL}{invoices.a.pk}/", **auth(data["access"]))
    assert response.status_code == 200
    assert response.data["id"] == invoices.a.pk


@pytest.mark.django_db
def test_spec_out_of_scope_detail_returns_404(api, analyst, invoices) -> None:
    data = login(api)
    response = api.get(f"{INVOICES_URL}{invoices.outside.pk}/", **auth(data["access"]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_spec_customer_sees_only_own_invoice(api, customer, analyst, invoices) -> None:
    data = login(api, username="customer")
    listing = api.get(INVOICES_URL, **auth(data["access"]))
    assert [row["id"] for row in listing.data] == [invoices.own.pk]
    assert api.get(f"{INVOICES_URL}{invoices.a.pk}/", **auth(data["access"])).status_code == 404
    assert api.get(f"{INVOICES_URL}{invoices.own.pk}/", **auth(data["access"])).status_code == 200


@pytest.mark.django_db
def test_spec_analyst_sees_only_remaining_branch_after_membership_removal(
    api, analyst, invoices
) -> None:
    data = login(api)
    before = api.get(INVOICES_URL, **auth(data["access"]))
    assert {row["id"] for row in before.data} == {invoices.a.pk, invoices.b.pk}
    Membership.objects.filter(user=analyst, branch=invoices.a.branch).delete()
    after = api.get(INVOICES_URL, **auth(data["access"]))
    assert {row["id"] for row in after.data} == {invoices.b.pk}
    detail = api.get(f"{INVOICES_URL}{invoices.a.pk}/", **auth(data["access"]))
    assert detail.status_code == 404


@pytest.mark.django_db
def test_spec_membership_checked_live_each_request(api, analyst, invoices) -> None:
    data = login(api)
    membership = Membership.objects.get(user=analyst, branch=invoices.a.branch)
    assert api.get(f"{INVOICES_URL}{invoices.a.pk}/", **auth(data["access"])).status_code == 200
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    assert api.get(f"{INVOICES_URL}{invoices.a.pk}/", **auth(data["access"])).status_code == 404
    membership.is_active = True
    membership.save(update_fields=["is_active"])
    assert api.get(f"{INVOICES_URL}{invoices.a.pk}/", **auth(data["access"])).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["list", "detail"])
def test_spec_get_queryset_is_scoped_for_every_action(api, analyst, invoices, action) -> None:
    """The IDOR fix: both list and detail go through visible_invoices()."""
    data = login(api)
    if action == "list":
        response = api.get(INVOICES_URL, **auth(data["access"]))
        assert invoices.outside.pk not in {row["id"] for row in response.data}
    else:
        response = api.get(f"{INVOICES_URL}{invoices.outside.pk}/", **auth(data["access"]))
        assert response.status_code == 404


@pytest.mark.django_db
def test_spec_expired_access_token_returns_401(api, analyst, invoices, monkeypatch) -> None:
    data = login(api)
    original = tokens.utcnow

    def past_clock():
        return original() + timedelta(minutes=6)

    monkeypatch.setattr(tokens, "utcnow", past_clock)
    response = api.get(INVOICES_URL, **auth(data["access"]))
    assert response.status_code == 401


@pytest.mark.django_db
def test_spec_missing_token_returns_401(api, analyst) -> None:
    assert api.get(INVOICES_URL).status_code == 401


@pytest.mark.django_db
def test_spec_malformed_token_returns_401(api, analyst) -> None:
    assert api.get(INVOICES_URL, **auth("not-a-jwt")).status_code == 401


@pytest.mark.django_db
def test_spec_refresh_token_used_as_bearer_returns_401(api, analyst) -> None:
    pair = login(api)
    assert api.get(INVOICES_URL, **auth(pair["refresh"])).status_code == 401
