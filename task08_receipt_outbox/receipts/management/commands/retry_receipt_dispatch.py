"""Operator command to re-pursue a failed receipt dispatch."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from receipts.models import OutboxAttempt, OutboxMessage
from receipts.services import enqueue_dispatch


class Command(BaseCommand):
    help = "Reset a failed outbox row and dispatch it again with the same key."

    def add_arguments(self, parser: object) -> None:
        parser.add_argument("message_id", type=int)

    def handle(self, *args: object, **options: object) -> None:
        message_id = options["message_id"]
        with transaction.atomic():
            try:
                outbox = OutboxMessage.objects.select_for_update().get(pk=message_id)
            except OutboxMessage.DoesNotExist as exc:
                raise CommandError(f"no outbox message with id {message_id}") from exc
            if outbox.status != OutboxMessage.Status.FAILED:
                raise CommandError(
                    f"outbox message {message_id} is {outbox.status}; "
                    "only failed rows can be retried"
                )
            outbox.status = OutboxMessage.Status.PENDING
            outbox.attempts = 0
            outbox.next_attempt_at = timezone.now()
            outbox.last_error = ""
            outbox.save(update_fields=["status", "attempts", "next_attempt_at", "last_error"])

        # Same helper as the sweeper: a broker outage leaves the PENDING row recoverable.
        enqueue_dispatch(message_id)
        self.stdout.write(f"requeued outbox message {message_id}")
        for attempt in OutboxAttempt.objects.filter(message_id=message_id).order_by("attempt_no"):
            detail = f" ({attempt.error})" if attempt.error else ""
            self.stdout.write(
                f"  attempt {attempt.attempt_no}: {attempt.outcome} "
                f"at {attempt.started_at.isoformat()}{detail}"
            )
