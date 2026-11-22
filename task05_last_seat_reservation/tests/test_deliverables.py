"""Deliverables: migration, real PostgreSQL, select_for_update and lock-order note."""

import inspect
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.db.models import UniqueConstraint
from django.test.utils import CaptureQueriesContext

from reservations import services
from reservations.db import ensure_database
from reservations.models import GymClass, Reservation
from reservations.services import reserve

CONSTRAINT_NAMES = {"uniq_reservation_user_class", "uniq_reservation_user_key"}
ROOT = Path(__file__).resolve().parents[1]


def test_spec_real_postgresql_not_sqlite() -> None:
    """Every test and every worker runs against PostgreSQL, never SQLite."""
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert connection.vendor == "postgresql"


def test_spec_migration_file_present() -> None:
    """A checked-in migration creates both unique constraints."""
    migration_dir = ROOT / "reservations" / "migrations"
    files = sorted(path for path in migration_dir.glob("0*.py"))
    assert files
    text = "\n".join(path.read_text() for path in files)
    assert all(name in text for name in CONSTRAINT_NAMES)


@pytest.mark.django_db
def test_spec_migration_creates_unique_constraints_in_database() -> None:
    """The unique constraints exist in the migrated PostgreSQL schema."""
    model_constraints = {
        item.name for item in Reservation._meta.constraints if isinstance(item, UniqueConstraint)
    }
    assert model_constraints == CONSTRAINT_NAMES
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'u'",
            [Reservation._meta.db_table],
        )
        database_constraints = {row[0] for row in cursor.fetchall()}
    assert database_constraints >= CONSTRAINT_NAMES


@pytest.mark.django_db
def test_spec_select_for_update_locks_class_row_first() -> None:
    """The first SELECT of reserve() locks the class row FOR UPDATE."""
    klass = GymClass.objects.create(name="Yoga", capacity=3)
    with CaptureQueriesContext(connection) as captured:
        reservation_id = reserve(klass.id, user_id=1, key="key-1")
    selects = [
        query["sql"] for query in captured.captured_queries if "SELECT" in query["sql"].upper()
    ]
    assert selects
    assert "reservations_gymclass" in selects[0]
    assert "FOR UPDATE" in selects[0].upper()
    assert Reservation.objects.filter(pk=reservation_id).exists()


def test_spec_no_in_process_lock() -> None:
    """The service must not rely on a process-local mutex."""
    source = inspect.getsource(services)
    assert "threading.Lock" not in source
    assert "RLock" not in source
    assert "Semaphore" not in source


def test_spec_ensure_database_is_idempotent() -> None:
    """ensure_database() is safe to call again after the database already exists."""
    ensure_database()
    ensure_database()


def test_spec_ensure_db_management_command() -> None:
    """`manage.py ensure_db` makes the task database available before migrate."""
    output = StringIO()
    call_command("ensure_db", stdout=output)
    assert "task05" in output.getvalue()


def test_spec_conftest_uses_shared_ensure_database() -> None:
    """The pytest fixture and the management command call the same helper."""
    text = (ROOT / "conftest.py").read_text()
    assert "ensure_database()" in text


def test_spec_lock_order_explained_in_readme() -> None:
    """The README explains why the class row is always locked first."""
    text = (ROOT / "README.md").read_text()
    lowered = text.lower()
    assert "lock order" in lowered
    assert "class row first" in lowered
    assert "never the reverse" in lowered
