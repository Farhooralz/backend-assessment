"""Celery entry points; the broker may vanish without losing durable rows."""

from celery_app import app
from receipts import services


@app.task(name="receipts.tasks.dispatch_receipt")
def dispatch_receipt(message_id: int) -> str:
    """Send one outbox message, using its idempotency key."""
    return services.process_outbox_message(message_id)


@app.task(name="receipts.tasks.sweep_outbox")
def sweep_outbox() -> int:
    """Requeue all due outbox rows (called by Celery beat every 5 seconds)."""
    return services.sweep_outbox()
