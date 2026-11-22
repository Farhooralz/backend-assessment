"""Spec-driven checks for the Task 10 design document and its checker."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "README.md"


def _doc() -> str:
    """Return the document text, or empty text while it is unwritten (red state)."""
    if not DOC_PATH.exists():
        return ""
    return DOC_PATH.read_text(encoding="utf-8")


def _headings(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.startswith("## ")]


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _mermaid_blocks(text: str) -> list[str]:
    return re.findall(r"```mermaid\s*\n(.*?)```", text, flags=re.DOTALL)


def _checker():
    path = ROOT / "check_doc.py"
    if not path.exists():
        pytest.fail("check_doc.py is missing (checker not implemented yet)")
    spec = importlib.util.spec_from_file_location("task10_check_doc", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_spec_document_exists() -> None:
    assert _doc().strip(), f"{DOC_PATH} is missing or empty"


def test_spec_architecture_scope_80_branches() -> None:
    text = _doc().lower()
    assert "80 branches" in text
    for concept in ("court reservation", "online payment", "financial reporting"):
        assert concept in text, f"missing scope concept: {concept}"


def test_spec_peak_load_inputs() -> None:
    text = _section(_doc(), "## Capacity model")
    for value in ("300", "3000", "150"):
        assert value in text, f"capacity model missing load input: {value}"


def test_spec_ten_minute_temporary_reservation() -> None:
    text = _doc().lower()
    assert "10 minute" in text
    assert "held" in text
    assert "sweeper" in text


def test_spec_no_overlapping_active_intervals() -> None:
    text = _doc().lower()
    assert "overlap" in text
    assert "tstzrange" in text
    assert "exclude" in text


def test_spec_late_payment_handling() -> None:
    text = _section(_doc(), "## Late-payment walkthrough").lower()
    assert "late payment" in text
    assert "expired" in text
    assert "refund" in text


def test_spec_repeated_callback_handling() -> None:
    text = _doc().lower()
    assert "idempotent" in text
    assert "provider reference" in text
    assert "unique" in text


def test_spec_branch_manager_data_scope() -> None:
    text = _doc().lower()
    assert "branch manager" in text
    assert "own branch" in text or "own data" in text


def test_spec_central_finance_aggregate_report() -> None:
    text = _doc().lower()
    assert "central finance" in text
    assert "aggregate" in text


def test_spec_report_staleness_five_minutes() -> None:
    text = _doc().lower()
    assert "5 minute" in text
    assert "read replica" in text or "materialized" in text


def test_spec_two_customers_same_interval() -> None:
    text = _section(_doc(), "## Late-payment walkthrough").lower()
    assert "customer a" in text and "customer b" in text
    assert "same interval" in text


def test_spec_late_payment_walkthrough_has_status_column() -> None:
    text = _section(_doc(), "## Late-payment walkthrough").lower()
    assert "reservation status" in text
    for status in ("held", "expired", "confirmed"):
        assert status in text, f"walkthrough missing status: {status}"


def test_spec_late_payment_walkthrough_has_money_column() -> None:
    text = _section(_doc(), "## Late-payment walkthrough").lower()
    assert "money" in text
    assert "refund" in text
    assert "no money" in text or "0 rial" in text or "not charged" in text


def test_spec_late_payment_walkthrough_has_user_message_column() -> None:
    text = _section(_doc(), "## Late-payment walkthrough").lower()
    assert "user message" in text
    assert "expired" in text
    assert "refund" in text


def test_spec_late_payment_walkthrough_has_reconciliation_column() -> None:
    text = _section(_doc(), "## Late-payment walkthrough").lower()
    assert "reconciliation" in text
    assert "reconciliation entry" in text
    assert "callback" in text


def test_spec_api_boundary_section() -> None:
    assert "## API boundary" in _headings(_doc())
    text = _section(_doc(), "## API boundary")
    for endpoint in (
        "POST /api/reservations",
        "POST /api/payments/callback",
        "GET /api/courts/{court_id}/availability",
        "GET /api/reports/finance",
    ):
        assert endpoint in text, f"API boundary missing endpoint: {endpoint}"


def test_spec_erd_section() -> None:
    assert "## ERD" in _headings(_doc())


def test_spec_erd_mermaid_diagram() -> None:
    blocks = _mermaid_blocks(_doc())
    assert any("erDiagram" in block for block in blocks), "no Mermaid erDiagram found"
    erd = next(block for block in blocks if "erDiagram" in block)
    for entity in ("COURT", "RESERVATION", "PAYMENT", "RECONCILIATION_ENTRY"):
        assert entity in erd, f"ERD missing entity: {entity}"


def test_spec_sequence_diagram_section() -> None:
    assert "## Sequence diagram" in _headings(_doc())


def test_spec_sequence_mermaid_diagram() -> None:
    blocks = _mermaid_blocks(_doc())
    assert any("sequenceDiagram" in block for block in blocks), "no Mermaid sequenceDiagram found"
    seq = next(block for block in blocks if "sequenceDiagram" in block)
    for actor in ("Customer A", "Customer B", "API", "Postgres", "Payment provider"):
        assert actor in seq, f"sequence diagram missing participant: {actor}"


def test_spec_capacity_model_section() -> None:
    assert "## Capacity model" in _headings(_doc())


def test_spec_exclusion_constraint_on_tstzrange() -> None:
    text = _doc().lower()
    assert "exclusion constraint" in text
    assert "tstzrange" in text


def test_spec_availability_cache_redis_ttl_invalidation() -> None:
    text = _doc().lower()
    for token in ("redis", "ttl", "invalidat"):
        assert token in text, f"availability cache missing: {token}"


def test_spec_hot_court_per_court_serialization() -> None:
    text = _doc().lower()
    assert "hot court" in text
    assert "per-court" in text
    assert "serializ" in text or "advisory lock" in text


def test_spec_slo_section() -> None:
    assert "## SLO" in _headings(_doc())


def test_spec_p95_capacity_viewing_250_ms() -> None:
    text = _section(_doc(), "## SLO").lower()
    assert "p95" in text
    assert "250 ms" in text
    assert "availability" in text or "capacity viewing" in text


def test_spec_indicators_and_alerts_section() -> None:
    assert "## Indicators and alerts" in _headings(_doc())
    text = _section(_doc(), "## Indicators and alerts").lower()
    assert "alert" in text
    indicators = ("p95", "error rate", "cache hit rate", "callback", "sweep")
    found = [name for name in indicators if name in text]
    assert len(found) >= 4, f"too few indicators documented: {found}"


def test_spec_recovery_plan_section() -> None:
    assert "## Recovery plan" in _headings(_doc())
    text = _section(_doc(), "## Recovery plan").lower()
    for token in ("retry", "replay", "reconcil"):
        assert token in text, f"recovery plan missing: {token}"


def test_spec_load_test_section() -> None:
    assert "## Load test plan" in _headings(_doc())
    text = _section(_doc(), "## Load test plan").lower()
    for token in ("ramp", "300", "3000", "150", "p95", "pass criteria"):
        assert token in text, f"load test plan missing: {token}"


def test_spec_assumptions_section() -> None:
    assert "## Assumptions" in _headings(_doc())
    assert _section(_doc(), "## Assumptions").strip()


def test_spec_two_decisions_with_cost_or_limitation() -> None:
    assert "## Decisions and limitations" in _headings(_doc())
    text = _section(_doc(), "## Decisions and limitations").lower()
    for token in ("decision 1", "decision 2", "cost", "limitation"):
        assert token in text, f"decisions section missing: {token}"


def test_spec_implementation_not_required() -> None:
    text = _doc().lower()
    assert "implementation is not required" in text or "no implementation" in text


def test_spec_run_and_test_commands_documented() -> None:
    text = _section(_doc(), "## Run and test commands")
    assert "pip install -r requirements.txt" in text
    assert "python check_doc.py" in text
    assert "python -m pytest -q" in text


def test_spec_unfinished_parts_documented() -> None:
    assert "## Unfinished parts" in _headings(_doc())
    assert _section(_doc(), "## Unfinished parts").strip()


def test_spec_spot_check_record_documented() -> None:
    assert "## Spot-check record" in _headings(_doc())
    text = _section(_doc(), "## Spot-check record")
    for token in ("Mutation 1", "Mutation 2", "Mutation 3"):
        assert token in text, f"spot-check record missing: {token}"


def test_spec_checker_accepts_complete_document() -> None:
    checker = _checker()
    assert checker.check_document(_doc()) == []


def test_spec_checker_detects_missing_section() -> None:
    checker = _checker()
    damaged = _doc().replace("## SLO\n", "")
    errors = checker.check_document(damaged)
    assert any("## SLO" in error for error in errors), errors


def test_spec_checker_detects_missing_mermaid_diagram() -> None:
    checker = _checker()
    damaged = re.sub(r"```mermaid\s*\n.*?```", "", _doc(), flags=re.DOTALL)
    errors = checker.check_document(damaged)
    assert any("sequenceDiagram" in error for error in errors), errors
    assert any("erDiagram" in error for error in errors), errors


def test_spec_checker_cli_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "check_doc.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"stdout={result.stdout} stderr={result.stderr}"
    assert "OK:" in result.stdout
