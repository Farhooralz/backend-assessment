"""Read-only representation of an invoice."""

from rest_framework import serializers

from access.models import Invoice


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ["id", "number", "branch", "customer", "amount", "created_at"]
        read_only_fields = fields
