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


def _diagram(text: str, kind: str) -> str:
    """Return the first Mermaid diagram of the requested kind."""
    return next((block for block in _mermaid_blocks(text) if kind in block), "")


def _entity(erd: str, name: str) -> str:
    """Return the attribute body of one Mermaid ERD entity."""
    match = re.search(rf"\b{name}\s*\{{(.*?)\}}", erd, flags=re.DOTALL)
    return match.group(1) if match else ""


def _compact(text: str) -> str:
    """Normalize multiplication signs and whitespace to match sizing equations."""
    return re.sub(r"\s+", "", text.replace("×", "*").replace("·", "*"))


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


def test_spec_partial_exclusion_constraint_with_btree_gist() -> None:
    compact = _compact(_doc())
    assert re.search(
        r"EXCLUDEUSINGgist\(court_idWITH=,reserved_intervalWITH&&\)"
        r"WHEREstatusIN\('held','confirmed'\)",
        compact,
        flags=re.IGNORECASE,
    ), "exclusion constraint must be partial and guard reserved_interval"
    assert re.search(r"CREATEEXTENSION(?:IFNOTEXISTS)?btree_gist", compact, flags=re.IGNORECASE), (
        "btree_gist extension must be enabled for the = operator"
    )


def test_spec_unpartial_constraint_would_break_second_customer() -> None:
    text = _section(_doc(), "## ERD").lower()
    assert "without the where clause" in text
    assert "expired holds" in text
    assert "b takes the interval" in text
    assert "impossible" in text


def test_spec_erd_reserved_interval_on_reservation_only() -> None:
    erd = _diagram(_doc(), "erDiagram")
    assert "reserved_interval" in _entity(erd, "RESERVATION"), (
        "reserved_interval must be an attribute of RESERVATION"
    )
    assert "tstzrange" in _entity(erd, "RESERVATION")
    assert "reserved_interval" not in _entity(erd, "COURT"), "COURT must not own reserved_interval"


def test_spec_erd_unique_provider_reference_on_payment_only() -> None:
    erd = _diagram(_doc(), "erDiagram")
    assert "provider_reference" not in _entity(erd, "RESERVATION")
    payment = _entity(erd, "PAYMENT").lower()
    assert "text provider_reference" in payment
    assert "uk" in payment


def test_spec_erd_one_to_many_payment_attempts_callbacks() -> None:
    erd = _diagram(_doc(), "erDiagram")
    for child in ("PAYMENT", "PAYMENT_ATTEMPT", "CALLBACK_EVENT"):
        assert re.search(rf"RESERVATION\s+\|\|--o\{{\s+{child}\b", erd), (
            f"RESERVATION to {child} must be 1:N"
        )
    assert not re.search(r"RESERVATION\s+\|\|--o\|\s+PAYMENT\b", erd), (
        "payments are not 1:0..1: retries and late payments need 1:N"
    )
    text = _section(_doc(), "## ERD").lower()
    assert "retries" in text and "late payment" in text


def test_spec_sequence_notes_cover_status_money_message_reconciliation() -> None:
    seq = _diagram(_doc(), "sequenceDiagram")
    complete = [
        note
        for note in re.findall(r"Note over[^\n]*", seq)
        if all(field in note.lower() for field in ("status", "money", "message", "reconcil"))
    ]
    assert len(complete) >= 7, f"only {len(complete)} complete late-payment notes"
    for token in ("b takes the interval", "late payment", "repeated callback", "confirmed"):
        assert token in seq.lower(), f"sequence diagram missing step: {token}"


def test_spec_report_staleness_budget_is_bounded() -> None:
    text = (
        _section(_doc(), "## Capacity model")
        + _section(_doc(), "## SLO")
        + _section(_doc(), "## Decisions and limitations")
    ).lower()
    assert "exceed 5 minutes" in text or "exceeds 5 minutes" in text, (
        "must state that a replica-lagged materialized view can exceed 5 minutes"
    )
    assert "replica lag" in text and "refresh" in text
    assert "2min+3min=5min" in _compact(text), "staleness budget arithmetic is missing"
    assert "primary" in text and "timestamp" in text


def test_spec_capacity_model_sizing_arithmetic() -> None:
    compact = _compact(_section(_doc(), "## Capacity model"))
    # Round 2 replaced the flawed 4 ms advisory-lock budget with the SET NX gate arithmetic.
    for equation in (
        "3000*0.25=750",
        "300*0.25=75",
        "150*0.010=1.5",
        "150*0.002=0.3",
        "0.3/(1-0.3)*2=0.86",
        "1/600=0.0017",
        "150*0.010/6=0.25",
        "300*0.01=3",
        "750/50=15",
    ):
        assert equation in compact, f"capacity model missing arithmetic: {equation}"


def test_spec_multiple_slo_targets() -> None:
    section = _section(_doc(), "## SLO")
    rows = [
        line
        for line in section.splitlines()
        if line.startswith("|")
        and not re.match(r"\|\s*-", line)
        and "objective" not in line.lower()
    ]
    assert len(rows) >= 4, f"expected at least four SLOs, found {len(rows)}"
    for token in ("250 ms", "reservation commit", "callback", "staleness"):
        assert token in section.lower(), f"SLO section missing objective: {token}"
    assert re.search(r"(?:≤|<=)\s*5\s*min", section) or "5 minutes" in section


def test_spec_checker_detects_partial_constraint_regression() -> None:
    checker = _checker()
    damaged = _doc().replace(" WHERE status IN ('held','confirmed')", "")
    errors = checker.check_document(damaged)
    assert any("partial" in error for error in errors), errors


def test_spec_checker_detects_btree_gist_regression() -> None:
    checker = _checker()
    damaged = _doc().replace("btree_gist", "plain_gist")
    errors = checker.check_document(damaged)
    assert any("btree_gist" in error for error in errors), errors


def test_spec_checker_detects_erd_regressions() -> None:
    checker = _checker()
    damaged = _doc().replace("RESERVATION ||--o{ PAYMENT", "RESERVATION ||--o| PAYMENT")
    errors = checker.check_document(damaged)
    assert any("1:N" in error for error in errors), errors
    damaged = re.sub(
        r"(RESERVATION \{\n.*?)tstzrange reserved_interval",
        r"\1tstzrange wrong_name",
        _doc(),
        flags=re.DOTALL,
    )
    errors = checker.check_document(damaged)
    assert any("reserved_interval" in error and "RESERVATION" in error for error in errors)


def test_spec_checker_detects_staleness_and_sizing_regressions() -> None:
    checker = _checker()
    damaged = "\n".join(
        line for line in _doc().splitlines() if "2 min + worst-case replica lag" not in line
    )
    errors = checker.check_document(damaged)
    assert any("staleness budget" in error for error in errors), errors
    damaged = "\n".join(line for line in _doc().splitlines() if "3000 × 0.25 = 750" not in line)
    errors = checker.check_document(damaged)
    assert any("sizing arithmetic" in error for error in errors), errors


def test_spec_checker_detects_single_slo_regression() -> None:
    checker = _checker()
    damaged = "\n".join(
        line for line in _doc().splitlines() if "callback processing" not in line.lower()
    )
    errors = checker.check_document(damaged)
    assert any("SLO" in error for error in errors), errors
