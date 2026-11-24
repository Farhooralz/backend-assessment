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


class LoginRequestSerializer(serializers.Serializer):
    """Documented body for POST /api/token/."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class RefreshRequestSerializer(serializers.Serializer):
    """Documented body for POST /api/token/refresh/."""

    refresh = serializers.CharField()


class LogoutRequestSerializer(serializers.Serializer):
    """Documented body: either empty (Bearer header) or a refresh token."""

    refresh = serializers.CharField(required=False)


class TokenPairSerializer(serializers.Serializer):
    """The only success body issued by the token endpoints."""

    access = serializers.CharField()
    refresh = serializers.CharField()


class DetailSerializer(serializers.Serializer):
    """Error body shared by the token endpoints."""

    detail = serializers.CharField()


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ["id", "number", "branch", "customer", "amount", "created_at"]
        read_only_fields = fields
