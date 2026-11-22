"""Operator entry point for the idempotent database setup."""

from django.core.management.base import BaseCommand

from db_utils import DEFAULT_DB_NAME, ensure_database


class Command(BaseCommand):
    help = "Create the task08 database if it does not exist (safe to repeat)."

    def handle(self, *args: object, **options: object) -> None:
        ensure_database()
        self.stdout.write(f"database {DEFAULT_DB_NAME} is ready")
