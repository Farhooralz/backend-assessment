"""Request-shape validation and read-only invoice representation."""

from rest_framework import serializers

from access.models import Invoice


def valid_body(data: object, *required: str) -> dict[str, str] | None:
    """Return a string-only mapping, or None when the body is malformed.

    Rejecting non-mappings and non-string values here turns bad client input into
    a 400 at the HTTP layer instead of an AttributeError/TypeError deeper in the
    token helpers.
    """
    if not isinstance(data, dict):
        return None
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in data.items()):
        return None
    if any(name not in data for name in required):
        return None
    return dict(data)


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ["id", "number", "branch", "customer", "amount", "created_at"]
        read_only_fields = fields
