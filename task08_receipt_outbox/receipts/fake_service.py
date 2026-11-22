"""Fake receipt service: one message per key, with four explicit failure modes."""

from dataclasses import dataclass

from receipts.models import FakeExternalMessage

MODES = ("ok", "temporary_error", "permanent_error", "accept_then_timeout")
_mode = "ok"


class TemporaryReceiptError(RuntimeError):
    """Retryable failure: the service did not accept the message."""


class PermanentReceiptError(RuntimeError):
    """Non-retryable failure: the service refused the message permanently."""


class ReceiptTimeoutError(RuntimeError):
    """The service may have accepted the message but the response was lost."""


@dataclass(frozen=True, slots=True)
class SendResult:
    external_message_id: str


def set_fake_mode(mode: str) -> None:
    """Select the Fake's behavior for the current process."""
    global _mode
    if mode not in MODES:
        raise ValueError(f"unknown fake mode: {mode}")
    _mode = mode


def get_fake_mode() -> str:
    """Return the active Fake mode."""
    return _mode


class FakeReceiptService:
    """Accepts at most one external message per idempotency key."""

    def __init__(self, mode: str | None = None) -> None:
        self.mode = mode or get_fake_mode()

    def send(self, idempotency_key: str, payload: dict) -> SendResult:
        """Return the stored result for a repeated key instead of sending twice."""
        existing = FakeExternalMessage.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return SendResult(str(existing.pk))
        if self.mode == "ok":
            return self._accept(idempotency_key, payload)
        if self.mode == "accept_then_timeout":
            self._accept(idempotency_key, payload)
            raise ReceiptTimeoutError("response timed out after acceptance")
        if self.mode == "permanent_error":
            raise PermanentReceiptError("permanent receipt rejection")
        raise TemporaryReceiptError("temporary receipt failure")

    def lookup(self, idempotency_key: str) -> SendResult | None:
        """Check whether a timed-out send was actually accepted."""
        existing = FakeExternalMessage.objects.filter(idempotency_key=idempotency_key).first()
        return SendResult(str(existing.pk)) if existing is not None else None

    def _accept(self, idempotency_key: str, payload: dict) -> SendResult:
        message = FakeExternalMessage.objects.create(
            idempotency_key=idempotency_key, payload=payload
        )
        return SendResult(str(message.pk))
