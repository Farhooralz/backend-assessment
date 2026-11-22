"""Fail-closed configuration: no secret means settings cannot be imported."""

import runpy
import secrets
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SETTINGS_PATH = str(Path(sys.modules[settings.SETTINGS_MODULE].__file__))


def test_spec_settings_fail_closed_without_django_secret(monkeypatch) -> None:
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        runpy.run_path(SETTINGS_PATH)


def test_spec_settings_fail_closed_without_jwt_secret(monkeypatch) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ImproperlyConfigured, match="JWT_SECRET_KEY"):
        runpy.run_path(SETTINGS_PATH)


def test_spec_settings_fail_closed_on_blank_secret(monkeypatch) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", "   ")
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_urlsafe(48))
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        runpy.run_path(SETTINGS_PATH)


def test_spec_settings_use_environment_secrets(monkeypatch) -> None:
    django_key = secrets.token_urlsafe(48)
    jwt_key = secrets.token_urlsafe(48)
    monkeypatch.setenv("DJANGO_SECRET_KEY", django_key)
    monkeypatch.setenv("JWT_SECRET_KEY", jwt_key)
    namespace = runpy.run_path(SETTINGS_PATH)
    assert namespace["SECRET_KEY"] == django_key
    assert namespace["JWT_SECRET_KEY"] == jwt_key


def test_spec_allowed_hosts_comes_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("ALLOWED_HOSTS", "example.com, api.example.com")
    namespace = runpy.run_path(SETTINGS_PATH)
    assert namespace["ALLOWED_HOSTS"] == ["example.com", "api.example.com"]


def test_spec_settings_reject_short_jwt_secret(monkeypatch) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 31)
    with pytest.raises(ImproperlyConfigured, match="at least 32 bytes"):
        runpy.run_path(SETTINGS_PATH)
