"""Fail-closed configuration: a missing key must stop settings from loading."""

import runpy
import secrets
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SETTINGS_PATH = str(Path(sys.modules[settings.SETTINGS_MODULE].__file__))


def test_spec_settings_fail_closed_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        runpy.run_path(SETTINGS_PATH)


def test_spec_settings_fail_closed_on_blank_secret(monkeypatch) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", "   ")
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        runpy.run_path(SETTINGS_PATH)


def test_spec_settings_secret_key_comes_from_env(monkeypatch) -> None:
    key = secrets.token_urlsafe(48)
    monkeypatch.setenv("DJANGO_SECRET_KEY", key)
    namespace = runpy.run_path(SETTINGS_PATH)
    assert namespace["SECRET_KEY"] == key


def test_spec_settings_allowed_hosts_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("ALLOWED_HOSTS", "a.example.com, b.example.com ,")
    namespace = runpy.run_path(SETTINGS_PATH)
    assert namespace["ALLOWED_HOSTS"] == ["a.example.com", "b.example.com"]


def test_spec_settings_allowed_hosts_default(monkeypatch) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    namespace = runpy.run_path(SETTINGS_PATH)
    assert namespace["ALLOWED_HOSTS"] == ["localhost", "127.0.0.1"]
