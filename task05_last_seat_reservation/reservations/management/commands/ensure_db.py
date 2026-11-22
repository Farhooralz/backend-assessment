"""Expose ensure_database() so a fresh checkout can be migrated before pytest."""

from django.core.management.base import BaseCommand

from reservations.db import DB_NAME, ensure_database


class Command(BaseCommand):
    """Create the isolated task database idempotently."""

    help = f"Create the {DB_NAME} database if it does not exist."

    def handle(self, *args: object, **options: object) -> None:
        """Create the database if needed and report that it is ready."""
        ensure_database()
        self.stdout.write(f"Database {DB_NAME} is ready.")
