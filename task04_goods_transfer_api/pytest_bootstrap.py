"""Test-only bootstrap: supply an ephemeral key before Django settings load.

Production never imports this module; ``settings.py`` fails closed without an
environment value. Tests that already export a key keep it.
"""

import os
import secrets

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(
    early_config: pytest.Config, parser: pytest.Parser, args: list[str]
) -> None:
    """Run before pytest-django imports settings and fill only a missing key."""
    if not os.environ.get("DJANGO_SECRET_KEY", "").strip():
        os.environ["DJANGO_SECRET_KEY"] = secrets.token_urlsafe(48)
