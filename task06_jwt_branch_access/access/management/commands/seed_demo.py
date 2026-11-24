"""Idempotent demo data for the manual API walkthrough."""

import os
import secrets
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.management.base import BaseCommand
from django.db import transaction

from access.models import Branch, Invoice, Membership

ANALYST_USERNAME = "demo_analyst"
CUSTOMER_USERNAME = "demo_customer"
USERNAMES = (ANALYST_USERNAME, CUSTOMER_USERNAME)
DEMO_INVOICES = (
    ("DEMO-A-1", "Demo A", None, Decimal("150.00")),
    ("DEMO-B-1", "Demo B", None, Decimal("275.50")),
    ("DEMO-CUST-1", "Demo outside", CUSTOMER_USERNAME, Decimal("49.90")),
)


class Command(BaseCommand):
    help = "Create demo branches, users and invoices; safe to run repeatedly."

    @transaction.atomic
    def handle(self, *args: str, **options: object) -> None:
        users = {name: self._find_user(name) for name in USERNAMES}
        configured = os.environ.get("DEMO_PASSWORD")
        generated = not configured and any(user is None for user in users.values())
        password = configured or (secrets.token_urlsafe(18) if generated else None)

        for username, user in users.items():
            if user is None:
                user = get_user_model().objects.create(username=username)
            if password is not None:
                user.set_password(password)
                user.save(update_fields=["password"])

        branches = {
            name: Branch.objects.get_or_create(name=name)[0]
            for name in ("Demo A", "Demo B", "Demo outside")
        }
        analyst = get_user_model().objects.get(username=ANALYST_USERNAME)
        customer = get_user_model().objects.get(username=CUSTOMER_USERNAME)
        for branch_name in ("Demo A", "Demo B"):
            Membership.objects.update_or_create(
                user=analyst,
                branch=branches[branch_name],
                role=Membership.ROLE_ANALYST,
                defaults={"is_active": True},
            )
        Membership.objects.update_or_create(
            user=customer,
            branch=branches["Demo A"],
            role=Membership.ROLE_CUSTOMER,
            defaults={"is_active": True},
        )
        for number, branch_name, customer_name, amount in DEMO_INVOICES:
            Invoice.objects.get_or_create(
                number=number,
                defaults={
                    "branch": branches[branch_name],
                    "customer": (
                        get_user_model().objects.get(username=customer_name)
                        if customer_name
                        else None
                    ),
                    "amount": amount,
                },
            )

        if generated:
            self.stdout.write(f"demo password: {password}")
        self.stdout.write("demo usernames: " + ", ".join(USERNAMES))

    @staticmethod
    def _find_user(username: str) -> AbstractBaseUser | None:
        return get_user_model().objects.filter(username=username).first()
