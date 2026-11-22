"""Test-only bootstrap: supply ephemeral random keys before Django settings load.

Production never imports this module; ``settings.py`` fails closed without real
environment values. Tests that already export keys (for example via ``../.env``)
keep them, so no development key literal ever lives in source.
"""

import os
import secrets

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(
    early_config: pytest.Config, parser: pytest.Parser, args: list[str]
) -> None:
    """Run before pytest-django imports settings and fill only missing keys."""
    if not os.environ.get("DJANGO_SECRET_KEY"):
        os.environ["DJANGO_SECRET_KEY"] = secrets.token_urlsafe(48)
    if not os.environ.get("JWT_SECRET_KEY"):
        os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
