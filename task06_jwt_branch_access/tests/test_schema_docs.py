"""Round 3 contract: the API is browsable without weakening its permissions."""

import pytest
import yaml
from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

EXPECTED_PATHS = {
    "/api/token/",
    "/api/token/refresh/",
    "/api/token/logout/",
    "/api/invoices/",
    "/api/invoices/{id}/",
}
PROTECTED_URL = "/api/invoices/"


def generated_schema() -> dict:
    """Build the same document the ``spectacular`` command serves at /api/schema/."""
    return SchemaGenerator().get_schema(request=None, public=True)


def resolve(document: dict, schema: dict) -> dict:
    """Follow a local $ref so component-based request bodies can be inspected."""
    if "$ref" in schema:
        return document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def test_spec_spectacular_validate_reports_no_errors_or_warnings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    call_command("spectacular", validate=True, fail_on_warn=True)
    captured = capsys.readouterr()
    document = yaml.safe_load(captured.out)
    assert "openapi" in document
    assert "paths" in document
    assert "warning" not in captured.err.lower()


def test_spec_docs_page_is_reachable_without_login() -> None:
    client = APIClient()
    assert client.get("/api/docs/").status_code == 200
    assert client.get("/api/schema/").status_code == 200


def test_spec_openapi_document_lists_every_endpoint() -> None:
    paths = set(generated_schema()["paths"])
    assert paths >= EXPECTED_PATHS


def test_spec_schema_documents_token_request_and_response_bodies() -> None:
    document = generated_schema()
    login = document["paths"]["/api/token/"]["post"]
    refresh = document["paths"]["/api/token/refresh/"]["post"]
    login_body = resolve(document, login["requestBody"]["content"]["application/json"]["schema"])
    refresh_body = resolve(
        document, refresh["requestBody"]["content"]["application/json"]["schema"]
    )
    assert {"username", "password"} <= set(login_body["properties"])
    assert "refresh" in refresh_body["properties"]
    for operation in (login, refresh):
        response = resolve(
            document, operation["responses"]["200"]["content"]["application/json"]["schema"]
        )
        assert {"access", "refresh"} <= set(response["properties"])


def test_spec_schema_advertises_bearer_access_token() -> None:
    document = generated_schema()
    security_schemes = document["components"]["securitySchemes"]
    assert security_schemes["bearerAuth"]["scheme"] == "bearer"
    assert security_schemes["bearerAuth"]["bearerFormat"] == "JWT"
    protected = document["paths"]["/api/invoices/"]["get"]
    assert protected["security"] == [{"bearerAuth": []}]


def test_spec_protected_endpoint_still_requires_authentication() -> None:
    response = APIClient().get(PROTECTED_URL)
    assert response.status_code in (401, 403)
