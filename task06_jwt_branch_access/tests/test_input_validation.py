"""Malformed request bodies must be rejected with 400, never a 500."""

import pytest

from tests.conftest import LOGIN_URL, LOGOUT_URL, REFRESH_URL, auth, login

BAD_BODIES = ([1, 2], None, {"username": 1, "password": "pw"})


def post_bad_body(api, url: str, body: object, **extra: object) -> object:
    """Send a real JSON ``null``; DRF otherwise turns a None data argument into ''."""
    if body is None:
        return api.post(url, "null", content_type="application/json", **extra)
    return api.post(url, body, format="json", **extra)


@pytest.mark.django_db
def test_spec_login_rejects_malformed_bodies(api) -> None:
    api.raise_request_exception = False
    for body in BAD_BODIES:
        assert post_bad_body(api, LOGIN_URL, body).status_code == 400


@pytest.mark.django_db
def test_spec_refresh_rejects_malformed_bodies(api) -> None:
    api.raise_request_exception = False
    for body in BAD_BODIES:
        assert post_bad_body(api, REFRESH_URL, body).status_code == 400


@pytest.mark.django_db
def test_spec_logout_rejects_malformed_bodies(api, analyst) -> None:
    access = login(api)["access"]
    api.raise_request_exception = False
    for body in BAD_BODIES:
        assert post_bad_body(api, LOGOUT_URL, body, **auth(access)).status_code == 400
