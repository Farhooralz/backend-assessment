"""Create the task database before running migrate on a fresh checkout."""

from django.core.management.base import BaseCommand

from reports.db_utils import DEFAULT_DB_NAME, ensure_database


class Command(BaseCommand):
    help = "Create the task03 database if it does not exist yet."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--name", default=DEFAULT_DB_NAME, help="Database name to ensure.")

    def handle(self, *args, **options) -> None:
        name: str = options["name"]
        ensure_database(name)
        self.stdout.write(f"Database {name} is ready.")
