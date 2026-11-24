"""Spec-driven tests for the goods transfer request cycle."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.viewsets import ModelViewSet

from transfer.models import TransferRequest

pytestmark = pytest.mark.django_db

LIST_URL = "/api/transfers/"

ROLE_MATRIX_CASES = [
    ("employee", "list", 200),
    ("employee", "create", 201),
    ("employee", "retrieve", 200),
    ("employee", "submit", 200),
    ("employee", "approve", 403),
    ("employee", "reject", 403),
    ("manager", "list", 200),
    ("manager", "create", 403),
    ("manager", "retrieve", 200),
    ("manager", "submit", 403),
    ("manager", "approve", 200),
    ("manager", "reject", 200),
    ("other_employee", "list", 200),
    ("other_employee", "create", 403),
    ("other_employee", "retrieve", 404),
    ("other_employee", "submit", 404),
    ("other_employee", "approve", 404),
    ("other_employee", "reject", 404),
    ("other_manager", "list", 200),
    ("other_manager", "create", 403),
    ("other_manager", "retrieve", 404),
    ("other_manager", "submit", 404),
    ("other_manager", "approve", 404),
    ("other_manager", "reject", 404),
    ("anonymous", "list", 401),
    ("anonymous", "create", 401),
    ("anonymous", "retrieve", 401),
    ("anonymous", "submit", 401),
    ("anonymous", "approve", 401),
    ("anonymous", "reject", 401),
    ("no_profile_user", "list", 403),
    ("no_profile_user", "create", 403),
    ("no_profile_user", "retrieve", 403),
    ("no_profile_user", "submit", 403),
    ("no_profile_user", "approve", 403),
    ("no_profile_user", "reject", 403),
]


def detail_url(pk: int) -> str:
    return f"/api/transfers/{pk}/"


def action_url(pk: int, action: str) -> str:
    return f"/api/transfers/{pk}/{action}/"


def post_create(client, source, destination, quantity=3, **extra):
    payload = {
        "source": source.pk,
        "destination": destination.pk,
        "item_name": "balls",
        "quantity": quantity,
    }
    payload.update(extra)
    return client.post(LIST_URL, payload, format="json")


def test_spec_serializer_permission_authentication_and_viewset_present():
    from transfer.permissions import TransferActionPermission
    from transfer.serializers import TransferRequestSerializer
    from transfer.views import TransferRequestViewSet

    assert issubclass(TransferRequestViewSet, ModelViewSet)
    assert TransferActionPermission in TransferRequestViewSet.permission_classes
    assert any(
        issubclass(cls, SessionAuthentication)
        for cls in TransferRequestViewSet.authentication_classes
    )
    assert TransferRequestSerializer().fields["status"].read_only is True
    assert TransferRequestSerializer().fields["decided_by"].read_only is True


def test_spec_sample_three_balls_draft_send_approve(
    api_client, employee, manager, branch_a, branch_b
):
    api_client.force_login(employee)
    created = post_create(api_client, branch_a, branch_b, quantity=3)
    assert created.status_code == 201, created.data
    assert created.data["status"] == "draft"
    pk = created.data["id"]

    sent = api_client.post(action_url(pk, "submit"), {}, format="json")
    assert sent.status_code == 200, sent.data
    assert sent.data["status"] == "submitted"

    api_client.force_login(manager)
    approved = api_client.post(action_url(pk, "approve"), {}, format="json")
    assert approved.status_code == 200, approved.data
    assert approved.data["status"] == "approved"
    assert approved.data["decided_by"] == manager.pk
    assert approved.data["decided_at"] is not None

    stored = TransferRequest.objects.get(pk=pk)
    assert stored.status == "approved"
    assert stored.decided_by == manager
    assert stored.decided_at.tzinfo is not None


def test_spec_reject_with_reason(api_client, employee, manager, submitted):
    api_client.force_login(manager)
    response = api_client.post(
        action_url(submitted.pk, "reject"), {"reason": "out of stock"}, format="json"
    )
    assert response.status_code == 200, response.data
    assert response.data["status"] == "rejected"
    assert response.data["reason"] == "out of stock"
    assert response.data["decided_by"] == manager.pk
    submitted.refresh_from_db()
    assert submitted.reason == "out of stock"


def test_spec_reject_without_reason_returns_400(api_client, manager, submitted):
    api_client.force_login(manager)
    response = api_client.post(action_url(submitted.pk, "reject"), {}, format="json")
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("first", "second"),
    [("approve", "reject"), ("reject", "approve"), ("approve", "approve"), ("reject", "reject")],
)
def test_spec_second_decision_returns_409(api_client, manager, submitted, first, second):
    api_client.force_login(manager)
    first_response = api_client.post(
        action_url(submitted.pk, first),
        {"reason": "out of stock"} if first == "reject" else {},
        format="json",
    )
    assert first_response.status_code == 200, first_response.data
    second_response = api_client.post(
        action_url(submitted.pk, second),
        {"reason": "late"} if second == "reject" else {},
        format="json",
    )
    assert second_response.status_code == 409, second_response.data


def test_spec_quantity_zero_returns_400(api_client, employee, branch_a, branch_b):
    api_client.force_login(employee)
    response = post_create(api_client, branch_a, branch_b, quantity=0)
    assert response.status_code == 400


def test_spec_quantity_negative_returns_400(api_client, employee, branch_a, branch_b):
    api_client.force_login(employee)
    response = post_create(api_client, branch_a, branch_b, quantity=-1)
    assert response.status_code == 400


def test_spec_same_source_destination_returns_400(api_client, employee, branch_b):
    api_client.force_login(employee)
    response = post_create(api_client, branch_b, branch_b)
    assert response.status_code == 400


def test_spec_status_is_read_only_on_create(api_client, employee, branch_a, branch_b):
    api_client.force_login(employee)
    response = post_create(api_client, branch_a, branch_b, status="approved")
    assert response.status_code == 201, response.data
    assert response.data["status"] == "draft"
    assert TransferRequest.objects.get(pk=response.data["id"]).status == "draft"


def test_spec_decision_fields_cannot_be_set_by_payload(
    api_client, employee, manager, branch_a, branch_b
):
    api_client.force_login(employee)
    created = post_create(
        api_client,
        branch_a,
        branch_b,
        decided_by=manager.pk,
        decided_at="2020-01-01T00:00:00Z",
    )
    assert created.status_code == 201, created.data
    assert created.data["decided_by"] is None
    assert created.data["decided_at"] is None

    api_client.post(action_url(created.data["id"], "submit"), {}, format="json")
    api_client.force_login(manager)
    approved = api_client.post(action_url(created.data["id"], "approve"), {}, format="json")
    assert approved.status_code == 200, approved.data
    assert approved.data["decided_by"] == manager.pk


def test_spec_creator_cannot_decide(api_client, employee, submitted):
    api_client.force_login(employee)
    assert (
        api_client.post(action_url(submitted.pk, "approve"), {}, format="json").status_code == 403
    )
    assert (
        api_client.post(
            action_url(submitted.pk, "reject"), {"reason": "no"}, format="json"
        ).status_code
        == 403
    )


@pytest.mark.parametrize("actor_name", ["other_employee", "other_manager"])
def test_spec_detail_outside_visibility_returns_404(request, api_client, submitted, actor_name):
    api_client.force_login(request.getfixturevalue(actor_name))
    response = api_client.get(detail_url(submitted.pk))
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("actor_name", "action", "payload"),
    [
        ("employee", "approve", {}),
        ("employee", "reject", {"reason": "no"}),
        ("manager", "submit", {}),
    ],
)
def test_spec_forbidden_action_on_visible_record_returns_403(
    request, api_client, submitted, actor_name, action, payload
):
    api_client.force_login(request.getfixturevalue(actor_name))
    response = api_client.post(action_url(submitted.pk, action), payload, format="json")
    assert response.status_code == 403, response.data


def test_spec_employee_sees_only_own_destination(
    api_client, employee, other_employee, branch_a, branch_b, branch_c
):
    api_client.force_login(employee)
    mine = post_create(api_client, branch_a, branch_b)
    api_client.force_login(other_employee)
    theirs = post_create(api_client, branch_a, branch_c)
    assert mine.status_code == 201 and theirs.status_code == 201

    api_client.force_login(employee)
    response = api_client.get(LIST_URL)
    assert response.status_code == 200
    ids = [row["id"] for row in response.data["results"]]
    assert ids == [mine.data["id"]]
    assert theirs.data["id"] not in ids


def test_spec_source_manager_sees_only_sent_requests_for_own_source(
    api_client, employee, manager, branch_a, branch_b, branch_c
):
    api_client.force_login(employee)
    mine = post_create(api_client, branch_a, branch_b)
    api_client.post(action_url(mine.data["id"], "submit"), {}, format="json")
    not_mine = post_create(api_client, branch_c, branch_b)
    api_client.post(action_url(not_mine.data["id"], "submit"), {}, format="json")
    draft_only = post_create(api_client, branch_a, branch_b)

    api_client.force_login(manager)
    response = api_client.get(LIST_URL)
    assert response.status_code == 200
    ids = [row["id"] for row in response.data["results"]]
    assert mine.data["id"] in ids
    assert not_mine.data["id"] not in ids
    assert draft_only.data["id"] not in ids

    decided = api_client.post(action_url(mine.data["id"], "approve"), {}, format="json")
    assert decided.status_code == 200
    # A decided request is still "sent"; it must remain addressable so a second
    # decision returns 409 rather than 404.
    assert api_client.get(detail_url(mine.data["id"])).status_code == 200


def test_spec_status_filter(api_client, employee, manager, branch_a, branch_b):
    api_client.force_login(employee)
    draft = post_create(api_client, branch_a, branch_b)
    sent = post_create(api_client, branch_a, branch_b)
    api_client.post(action_url(sent.data["id"], "submit"), {}, format="json")

    drafts = api_client.get(LIST_URL, {"status": "draft"})
    assert drafts.status_code == 200
    assert [row["id"] for row in drafts.data["results"]] == [draft.data["id"]]
    submitted = api_client.get(LIST_URL, {"status": "submitted"})
    assert [row["id"] for row in submitted.data["results"]] == [sent.data["id"]]
    assert api_client.get(LIST_URL, {"status": "unknown"}).status_code == 400

    api_client.force_login(manager)
    assert [
        row["id"] for row in api_client.get(LIST_URL, {"status": "draft"}).data["results"]
    ] == []


def test_spec_default_page_size_is_20(api_client, employee, branch_a, branch_b):
    api_client.force_login(employee)
    TransferRequest.objects.bulk_create(
        TransferRequest(
            source=branch_a,
            destination=branch_b,
            item_name="balls",
            quantity=1,
            created_by=employee,
        )
        for _ in range(21)
    )

    first = api_client.get(LIST_URL)
    assert first.status_code == 200
    assert first.data["count"] == 21
    assert len(first.data["results"]) == 20
    second = api_client.get(LIST_URL, {"page": 2})
    assert len(second.data["results"]) == 1


def test_spec_pagination_with_stable_ordering(api_client, employee, branch_a, branch_b):
    api_client.force_login(employee)
    created_ids = [post_create(api_client, branch_a, branch_b).data["id"] for _ in range(5)]
    now = timezone.now()
    for offset, pk in enumerate(created_ids):
        TransferRequest.objects.filter(pk=pk).update(created_at=now - timedelta(minutes=offset))

    seen = []
    for page in (1, 2, 3):
        response = api_client.get(LIST_URL, {"page": page, "page_size": 2})
        assert response.status_code == 200
        assert response.data["count"] == 5
        assert len(response.data["results"]) == (1 if page == 3 else 2)
        seen.extend(row["id"] for row in response.data["results"])
    assert seen == created_ids
    assert api_client.get(LIST_URL, {"page": 4, "page_size": 2}).status_code == 404


def test_spec_pagination_with_identical_created_at_stable_order(
    api_client, employee, branch_a, branch_b
):
    api_client.force_login(employee)
    created_ids = [post_create(api_client, branch_a, branch_b).data["id"] for _ in range(5)]
    stamp = timezone.now()
    TransferRequest.objects.filter(pk__in=created_ids).update(created_at=stamp)
    expected = sorted(created_ids, reverse=True)

    seen = []
    for page in (1, 2, 3):
        response = api_client.get(LIST_URL, {"page": page, "page_size": 2})
        assert response.status_code == 200
        assert response.data["count"] == 5
        seen.extend(row["id"] for row in response.data["results"])
    assert seen == expected
    assert len(set(seen)) == 5


def test_spec_second_employee_of_same_destination_cannot_submit(
    api_client, employee, second_employee, draft
):
    assert employee.staff.branch_id == second_employee.staff.branch_id
    api_client.force_login(second_employee)
    response = api_client.post(action_url(draft.pk, "submit"), {}, format="json")
    assert response.status_code == 403, response.data
    draft.refresh_from_db()
    assert draft.status == "draft"


def test_spec_employee_creating_for_other_destination_returns_403(
    api_client, employee, branch_a, branch_c
):
    api_client.force_login(employee)
    response = post_create(api_client, branch_a, branch_c)
    assert response.status_code == 403, response.data
    assert TransferRequest.objects.count() == 0


def test_spec_deliverable_role_matrix_counts_36_cases():
    """The README's 6 actors x 6 actions claim must match the behavioural matrix."""
    assert len(ROLE_MATRIX_CASES) == 36
    assert {case[0] for case in ROLE_MATRIX_CASES} == {
        "employee",
        "manager",
        "other_employee",
        "other_manager",
        "no_profile_user",
        "anonymous",
    }


@pytest.mark.parametrize(("role", "action", "expected"), ROLE_MATRIX_CASES)
def test_spec_role_matrix(
    request,
    api_client,
    employee,
    manager,
    other_employee,
    other_manager,
    no_profile_user,
    branch_a,
    branch_b,
    submitted,
    role,
    action,
    expected,
):
    actors = {
        "employee": employee,
        "manager": manager,
        "other_employee": other_employee,
        "other_manager": other_manager,
        "no_profile_user": no_profile_user,
        "anonymous": None,
    }
    actor = actors[role]
    if actor is not None:
        api_client.force_login(actor)

    fresh_draft = TransferRequest.objects.create(
        source=branch_a,
        destination=branch_b,
        item_name="balls",
        quantity=1,
        created_by=employee,
    )
    target = fresh_draft if action == "submit" and role == "employee" else submitted
    payload = {"reason": "out of stock"} if action == "reject" else {}

    if action == "list":
        response = api_client.get(LIST_URL)
    elif action == "create":
        response = post_create(api_client, branch_a, branch_b)
    elif action == "retrieve":
        response = api_client.get(detail_url(target.pk))
    else:
        response = api_client.post(action_url(target.pk, action), payload, format="json")
    assert response.status_code == expected, (role, action, response.status_code, response.data)


def test_spec_state_machine_rejects_invalid_transitions(api_client, employee, manager, submitted):
    api_client.force_login(employee)
    assert api_client.post(action_url(submitted.pk, "submit"), {}, format="json").status_code == 409

    api_client.force_login(manager)
    approved = api_client.post(action_url(submitted.pk, "approve"), {}, format="json")
    assert approved.status_code == 200
    api_client.force_login(employee)
    assert api_client.post(action_url(submitted.pk, "submit"), {}, format="json").status_code == 409


def test_spec_source_manager_cannot_act_on_draft_returns_404(api_client, manager, draft):
    api_client.force_login(manager)
    assert api_client.post(action_url(draft.pk, "approve"), {}, format="json").status_code == 404
