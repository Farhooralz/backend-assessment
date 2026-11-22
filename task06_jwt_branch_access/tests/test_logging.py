"""Prove that signing keys and bearer tokens never reach the logs."""

import logging

import pytest
from django.conf import settings

from tests.conftest import INVOICES_URL, LOGOUT_URL, REFRESH_URL, auth, login


@pytest.mark.django_db
def test_spec_no_tokens_or_key_in_logs(api, analyst, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        pair = login(api)
        access = pair["access"]
        refresh = pair["refresh"]
        api.get(INVOICES_URL, **auth(access))
        rotated = api.post(REFRESH_URL, {"refresh": refresh}, format="json").data["refresh"]
        api.post(LOGOUT_URL, **auth(access))
    text = caplog.text
    assert "login attempt" in text  # the capture is live, so the negative checks mean something
    assert settings.JWT_SECRET_KEY not in text
    assert settings.SECRET_KEY not in text
    assert access not in text
    assert refresh not in text
    assert rotated not in text
