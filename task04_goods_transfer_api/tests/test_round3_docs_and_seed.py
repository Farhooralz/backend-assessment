"""Round-3 deliverable tests: public API docs and the idempotent demo seed."""

import base64
import json
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command, get_commands
from drf_spectacular.drainage import GENERATOR_STATS
from rest_framework.test import APIClient

from transfer.models import Branch, Staff, TransferRequest

pytestmark = pytest.mark.django_db

DEMO_USERNAMES = {"demo_employee", "demo_manager", "demo_other_employee"}
DEMO_BRANCHES = {"Demo Source", "Demo Destination", "Demo Other"}
DOCUMENTED_PATHS = {
    "/api/schema/",
    "/api/transfers/",
    "/api/transfers/{id}/",
    "/api/transfers/{id}/submit/",
    "/api/transfers/{id}/approve/",
    "/api/transfers/{id}/reject/",
}


def basic_auth(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"HTTP_AUTHORIZATION": f"Basic {token}"}


def test_spec_schema_generates_without_errors_or_warnings(capsys: pytest.CaptureFixture[str]):
    """Equivalent to manage.py spectacular --validate --fail-on-warn."""
    assert "spectacular" in get_commands()
    GENERATOR_STATS.reset()
    output = StringIO()
    call_command(
        "spectacular", "--format=openapi-json", "--validate", "--fail-on-warn", stdout=output
    )
    schema = json.loads(output.getvalue())
    assert schema["openapi"].startswith("3.")
    assert capsys.readouterr().err == ""


def test_spec_docs_are_public_but_existing_endpoints_still_require_auth():
    client = APIClient()
    assert client.get("/api/docs/").status_code == 200
    assert client.get("/api/schema/").status_code == 200
    assert client.get("/api/transfers/").status_code == 401
    assert client.post("/api/transfers/", {}, format="json").status_code == 401
    assert client.get("/api/transfers/1/").status_code == 401


def test_spec_documented_paths_include_every_real_endpoint():
    response = APIClient().get("/api/schema/")
    assert response.status_code == 200
    paths = set(response.data["paths"])
    assert paths >= DOCUMENTED_PATHS
    assert set(response.data["paths"]["/api/transfers/"]) >= {"get", "post"}
    assert set(response.data["paths"]["/api/transfers/{id}/submit/"]) >= {"post"}
    assert set(response.data["paths"]["/api/transfers/{id}/approve/"]) >= {"post"}
    assert set(response.data["paths"]["/api/transfers/{id}/reject/"]) >= {"post"}


def test_spec_schema_describes_action_request_bodies():
    schema = APIClient().get("/api/schema/").data
    paths = schema["paths"]
    reject = paths["/api/transfers/{id}/reject/"]["post"]
    ref = reject["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    component = schema["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert set(component["properties"]) == {"reason"}
    assert "readOnly" not in component["properties"]["reason"]
    for path in ("/api/transfers/{id}/submit/", "/api/transfers/{id}/approve/"):
        assert "requestBody" not in paths[path]["post"]


def test_spec_seed_demo_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEMO_PASSWORD", "idempotent-demo-secret")
    first_output = StringIO()
    call_command("seed_demo", stdout=first_output)
    counts = (
        Branch.objects.count(),
        get_user_model().objects.count(),
        Staff.objects.count(),
        TransferRequest.objects.count(),
    )
    second_output = StringIO()
    call_command("seed_demo", stdout=second_output)
    assert (
        Branch.objects.count(),
        get_user_model().objects.count(),
        Staff.objects.count(),
        TransferRequest.objects.count(),
    ) == counts
    assert TransferRequest.objects.values("item_name").distinct().count() == counts[3]


def test_spec_seed_demo_creates_users_and_data_covering_the_flows(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DEMO_PASSWORD", "flow-demo-secret")
    output = StringIO()
    call_command("seed_demo", stdout=output)
    assert set(get_user_model().objects.values_list("username", flat=True)) >= DEMO_USERNAMES
    assert set(Branch.objects.values_list("name", flat=True)) >= DEMO_BRANCHES
    assert (Branch.objects.count(), get_user_model().objects.count(), Staff.objects.count()) == (
        3,
        3,
        3,
    )
    assert TransferRequest.objects.count() == 4
    assert set(TransferRequest.objects.values_list("status", flat=True)) == {
        TransferRequest.Status.DRAFT,
        TransferRequest.Status.SUBMITTED,
        TransferRequest.Status.APPROVED,
        TransferRequest.Status.REJECTED,
    }
    for username in DEMO_USERNAMES:
        assert username in output.getvalue()


def test_spec_seed_demo_generated_password_is_printed_once(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    first_output = StringIO()
    call_command("seed_demo", stdout=first_output)
    first = first_output.getvalue()
    assert "Demo password:" in first
    password = first.split("Demo password:", 1)[1].splitlines()[0].strip()
    assert password
    assert get_user_model().objects.get(username="demo_employee").check_password(password)

    second_output = StringIO()
    call_command("seed_demo", stdout=second_output)
    assert "Demo password:" not in second_output.getvalue()
    assert get_user_model().objects.get(username="demo_employee").check_password(password)


def test_spec_seed_demo_never_prints_a_supplied_password(monkeypatch: pytest.MonkeyPatch):
    secret = "supplied-demo-secret-42"
    monkeypatch.setenv("DEMO_PASSWORD", secret)
    output = StringIO()
    call_command("seed_demo", stdout=output)
    assert secret not in output.getvalue()
    assert "Demo password:" not in output.getvalue()
    assert get_user_model().objects.get(username="demo_manager").check_password(secret)


def test_spec_session_login_supports_swagger_cookie_auth(monkeypatch: pytest.MonkeyPatch):
    secret = "session-demo-secret"
    monkeypatch.setenv("DEMO_PASSWORD", secret)
    call_command("seed_demo", stdout=StringIO())
    client = APIClient()
    assert client.get("/api/auth/login/").status_code == 200
    logged_in = client.post("/api/auth/login/", {"username": "demo_employee", "password": secret})
    assert logged_in.status_code == 302
    assert client.cookies["sessionid"].value
    assert client.get("/api/transfers/").status_code == 200


def test_spec_seed_demo_supports_the_documented_curl_walkthrough(
    monkeypatch: pytest.MonkeyPatch,
):
    secret = "walkthrough-demo-secret"
    monkeypatch.setenv("DEMO_PASSWORD", secret)
    call_command("seed_demo", stdout=StringIO())
    source = Branch.objects.get(name="Demo Source").pk
    destination = Branch.objects.get(name="Demo Destination").pk
    other = Branch.objects.get(name="Demo Other").pk

    client = APIClient(**basic_auth("demo_employee", secret))
    created = client.post(
        "/api/transfers/",
        {"source": source, "destination": destination, "item_name": "balls", "quantity": 3},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["status"] == "draft"
    pk = created.data["id"]

    sent = client.post(f"/api/transfers/{pk}/submit/", {}, format="json")
    assert sent.status_code == 200, sent.data
    assert sent.data["status"] == "submitted"

    other_client = APIClient(**basic_auth("demo_other_employee", secret))
    foreign = other_client.post(
        "/api/transfers/",
        {"source": source, "destination": other, "item_name": "balls", "quantity": 1},
        format="json",
    )
    assert foreign.status_code == 201, foreign.data
    assert client.get(f"/api/transfers/{foreign.data['id']}/").status_code == 404
    assert client.post(f"/api/transfers/{pk}/approve/", {}, format="json").status_code == 403

    assert (
        client.post(
            "/api/transfers/",
            {"source": source, "destination": destination, "item_name": "balls", "quantity": 0},
            format="json",
        ).status_code
        == 400
    )

    manager = APIClient(**basic_auth("demo_manager", secret))
    approved = manager.post(f"/api/transfers/{pk}/approve/", {}, format="json")
    assert approved.status_code == 200, approved.data
    assert approved.data["decided_by"] is not None
    assert manager.post(f"/api/transfers/{pk}/approve/", {}, format="json").status_code == 409
