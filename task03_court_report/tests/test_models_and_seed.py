"""Spec tests for the data model, constraints, indexes and the seed command."""

from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction

from reports.management.commands.seed_bookings import Command as SeedCommand
from reports.models import Booking, Branch, Court, Payment, Tag

DATE_FROM = "2026-01-01"
DATE_TO = "2026-12-31"


@pytest.mark.django_db
def test_spec_models_migration_fk_and_many_to_many() -> None:
    migration = Path(__file__).resolve().parents[1] / "reports" / "migrations" / "0001_initial.py"
    assert migration.is_file()

    assert Booking._meta.get_field("court").remote_field.model is Court
    assert Payment._meta.get_field("booking").remote_field.model is Booking
    assert Court._meta.get_field("branch").remote_field.model is Branch
    assert Booking._meta.get_field("tags").many_to_many is True
    assert Booking._meta.get_field("tags").remote_field.model is Tag

    with connection.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {row[0] for row in cur.fetchall()}
    assert {
        "reports_branch",
        "reports_court",
        "reports_tag",
        "reports_booking",
        "reports_payment",
    } <= tables
    assert "reports_booking_tags" in tables


@pytest.mark.django_db
def test_spec_positive_amount_check_constraint() -> None:
    branch = Branch.objects.create(name="B")
    court = Court.objects.create(branch=branch, name="C")
    booking = Booking.objects.create(court=court, start_date="2026-01-15", confirmed=True)

    for bad in (Decimal("0"), Decimal("-1")):
        with pytest.raises(IntegrityError), transaction.atomic():
            Payment.objects.create(booking=booking, amount=bad, successful=True)

    good = Payment.objects.create(booking=booking, amount=Decimal("1"), successful=True)
    assert good.amount == Decimal("1")


@pytest.mark.django_db
def test_spec_suggested_indexes_exist() -> None:
    names = {idx.name for idx in Booking._meta.indexes}
    assert {"booking_court_start_idx", "booking_start_idx"} <= names

    with connection.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'reports_booking'")
        db_indexes = {row[0] for row in cur.fetchall()}
    assert {"booking_court_start_idx", "booking_start_idx"} <= db_indexes


def test_spec_seed_command_default_is_100000() -> None:
    parser = SeedCommand().create_parser("seed_bookings", "seed_bookings")
    args = parser.parse_args([])
    assert args.bookings == 100_000


@pytest.mark.django_db
@pytest.mark.timeout(120)
def test_spec_seed_command_creates_100000_bookings() -> None:
    call_command("seed_bookings", "--bookings", "100000", verbosity=0)
    assert Booking.objects.count() == 100_000
    assert Payment.objects.count() >= 100_000
    assert Booking.tags.through.objects.count() >= 100_000
