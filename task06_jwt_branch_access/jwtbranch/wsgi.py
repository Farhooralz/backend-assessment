"""WSGI entry point (kept minimal; the task is exercised through the test client)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jwtbranch.settings")

application = get_wsgi_application()
