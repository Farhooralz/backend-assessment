"""Idempotent demo data for the hand-on walkthrough in the README."""

import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from transfer.models import Branch, Staff, TransferRequest
from transfer.services import decide_request, submit_request

SOURCE_BRANCH = "Demo Source"
DESTINATION_BRANCH = "Demo Destination"
OTHER_BRANCH = "Demo Other"

DEMO_STAFF = (
    ("demo_employee", DESTINATION_BRANCH, Staff.Role.EMPLOYEE),
    ("demo_manager", SOURCE_BRANCH, Staff.Role.SOURCE_MANAGER),
    ("demo_other_employee", OTHER_BRANCH, Staff.Role.EMPLOYEE),
)

DEMO_REQUESTS = (
    ("demo balls - draft", 3, TransferRequest.Status.DRAFT),
    ("demo balls - submitted", 5, TransferRequest.Status.SUBMITTED),
    ("demo balls - approved", 3, TransferRequest.Status.APPROVED),
    ("demo balls - rejected", 2, TransferRequest.Status.REJECTED),
)


class Command(BaseCommand):
    help = "Seed demo branches, users and requests without creating duplicates."

    def handle(self, *args, **options) -> None:
        branches = {
            name: Branch.objects.get_or_create(name=name)[0]
            for name in (SOURCE_BRANCH, DESTINATION_BRANCH, OTHER_BRANCH)
        }
        supplied_password = os.environ.get("DEMO_PASSWORD", "")
        generated_password: str | None = None
        users = {}

        for username, branch_name, role in DEMO_STAFF:
            user, created = get_user_model().objects.get_or_create(username=username)
            if supplied_password:
                user.set_password(supplied_password)
                user.save(update_fields=["password"])
            elif created:
                if generated_password is None:
                    generated_password = secrets.token_urlsafe(18)
                user.set_password(generated_password)
                user.save(update_fields=["password"])
            Staff.objects.get_or_create(
                user=user,
                defaults={"branch": branches[branch_name], "role": role},
            )
            users[username] = user

        for item_name, quantity, target_status in DEMO_REQUESTS:
            request, created = TransferRequest.objects.get_or_create(
                source=branches[SOURCE_BRANCH],
                destination=branches[DESTINATION_BRANCH],
                item_name=item_name,
                created_by=users["demo_employee"],
                defaults={"quantity": quantity},
            )
            if not created:
                continue
            if target_status != TransferRequest.Status.DRAFT:
                submit_request(request, users["demo_employee"])
            if target_status in {
                TransferRequest.Status.APPROVED,
                TransferRequest.Status.REJECTED,
            }:
                decide_request(
                    request,
                    users["demo_manager"],
                    "approve" if target_status == TransferRequest.Status.APPROVED else "reject",
                    "demo: out of stock"
                    if target_status == TransferRequest.Status.REJECTED
                    else "",
                )

        for username, _, _ in DEMO_STAFF:
            self.stdout.write(f"Demo user: {username}")
        if generated_password is not None:
            self.stdout.write(f"Demo password: {generated_password}")
