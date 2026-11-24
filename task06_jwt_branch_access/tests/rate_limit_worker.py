"""Spawn-safe worker for the real-process rate-limit test.

Every Django import lives inside run(): a spawned interpreter imports this
module before django.setup() has been called.
"""

import os


def run(db_name: str, barrier, queue, username: str) -> None:
    """Open a connection, wait for the shared barrier, then post one bad login."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jwtbranch.settings")

    import django

    django.setup()

    from django.conf import settings

    settings.DATABASES["default"]["NAME"] = db_name  # pytest-django's test_task06
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]

    from django.db import connection
    from rest_framework.test import APIClient

    connection.ensure_connection()  # open the DB before waiting on the barrier
    try:
        barrier.wait(timeout=30)
        response = APIClient().post(
            "/api/token/", {"username": username, "password": "wrong"}, format="json"
        )
        queue.put(response.status_code)
    finally:
        connection.close()
