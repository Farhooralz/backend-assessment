"""Seed a large booking dataset for the report benchmark."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand

from reports.models import Booking, Branch, Court, Payment, Tag

BATCH = 5_000
COURTS = 20
TAGS = 10


class Command(BaseCommand):
    help = "Seed bookings (default 100,000) with payments and tags for benchmarking."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--bookings", type=int, default=100_000)
        parser.add_argument("--reset", action="store_true", help="Replace an existing dataset.")

    def handle(self, *args, **options) -> None:
        total: int = options["bookings"]
        if options["reset"]:
            Booking.objects.all().delete()  # cascades payments and tag links
        elif Booking.objects.exists():
            self.stdout.write("Already seeded; pass --reset to replace the dataset.")
            return
        branch, _ = Branch.objects.get_or_create(name="Seed Branch")
        courts = list(Court.objects.filter(branch=branch).order_by("id")[:COURTS])
        if len(courts) < COURTS:
            courts.extend(
                Court.objects.bulk_create(
                    Court(branch=branch, name=f"Seed Court {i}") for i in range(len(courts), COURTS)
                )
            )
        tags = list(Tag.objects.order_by("id")[:TAGS])
        if len(tags) < TAGS:
            tags.extend(
                Tag.objects.bulk_create(Tag(name=f"seed-tag-{i}") for i in range(len(tags), TAGS))
            )

        start = date(2026, 1, 1)
        through = Booking.tags.through
        for offset in range(0, total, BATCH):
            size = min(BATCH, total - offset)
            # Date, court and confirmation use coprime cycles: every court gets
            # bookings on every date, with both confirmed and unconfirmed rows.
            bookings = Booking.objects.bulk_create(
                Booking(
                    court=courts[i % COURTS],
                    start_date=start + timedelta(days=(i // COURTS) % 365),
                    confirmed=i % 7 != 0,
                )
                for i in range(offset, offset + size)
            )
            Payment.objects.bulk_create(
                Payment(
                    booking=booking,
                    amount=Decimal((i % 9 + 1) * 1000),
                    successful=i % 5 != 0,
                )
                for i, booking in enumerate(bookings, start=offset)
                for _ in range(2)
            )
            through.objects.bulk_create(
                through(booking_id=booking.id, tag_id=tags[(i + j) % TAGS].id)
                for i, booking in enumerate(bookings)
                for j in range(2)
            )
        if options.get("verbosity", 1):
            self.stdout.write(f"Seeded {total} bookings.")
