"""Idempotently create the task07 database from a fresh checkout."""

from django.core.management.base import BaseCommand

from ledger.db_utils import DB_NAME, ensure_database


class Command(BaseCommand):
    """Expose the shared bootstrap helper through ``manage.py ensure_db``."""

    help = f"Create the {DB_NAME} database if it does not exist yet."
    requires_system_checks = []
    requires_migrations_checks = False

    def handle(self, *args: object, **options: object) -> None:
        ensure_database()
        self.stdout.write(f"Database {DB_NAME} is ready.")
