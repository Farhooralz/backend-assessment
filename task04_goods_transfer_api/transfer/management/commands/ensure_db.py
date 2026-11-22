"""Create the per-task database so ``migrate`` works on a fresh setup."""

from django.core.management.base import BaseCommand

from transfer.db_bootstrap import DATABASE_NAME, ensure_database


class Command(BaseCommand):
    help = "Create the task04 database if it does not exist."

    def handle(self, *args, **options) -> None:
        created = ensure_database()
        state = "Created" if created else "Already present"
        self.stdout.write(f"{state} database '{DATABASE_NAME}'.")
