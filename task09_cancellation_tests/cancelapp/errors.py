"""Typed failures raised by the cancellation service."""


class CancellationError(Exception):
    """Base class for policy rejections."""


class PermissionDenied(CancellationError):
    """The requesting user may not cancel this reservation."""


class ReservationNotCancellable(CancellationError):
    """The reservation is not confirmed or has already started."""


class RefundDocumentWriteError(CancellationError):
    """Recording the refund document failed."""
