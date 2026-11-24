"""Create the configured task database if it does not exist yet."""

from django.conf import settings
from django.core.management.base import BaseCommand

from access.db_utils import ensure_database


class Command(BaseCommand):
    """Thin wrapper so a clean clone can bootstrap without a human-created database."""

    help = "Create this task's PostgreSQL database if it is missing (idempotent)."

    def handle(self, *args: str, **options: object) -> None:
        db_name = settings.DATABASES["default"]["NAME"]
        ensure_database(db_name)
        self.stdout.write(f"database {db_name} is ready")
