"""Round-2 regressions: external-review findings against the Task 10 design doc."""

from __future__ import annotations

import re
from pathlib import Path

import doc_rules

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "README.md"

INLINE_EXPIRY_SQL = (
    r"UPDATE\s+reservation\s+SET\s+status\s*=\s*'expired'"
    r"\s+WHERE\s+court_id\s*=\s*\?"
    r"\s+AND\s+status\s*=\s*'held'"
    r"\s+AND\s+expires_at\s*<=\s*now\(\)"
    r"\s+AND\s+reserved_interval\s+&&\s*\?"
)


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:
        return ""
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _diagram(text: str, kind: str) -> str:
    blocks = re.findall(r"```mermaid\s*\n(.*?)```", text, flags=re.DOTALL)
    return next((block for block in blocks if kind in block), "")


def _entity(erd: str, name: str) -> str:
    match = re.search(rf"\b{name}\s*\{{(.*?)\}}", erd, flags=re.DOTALL)
    return match.group(1) if match else ""


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text.replace("×", "*").replace("·", "*"))


def test_spec_inline_expiry_runs_before_insert_in_same_transaction() -> None:
    doc = _doc()
    assert "inline expiry" in doc.lower(), "insert path must document inline expiry"
    assert re.search(INLINE_EXPIRY_SQL, doc, flags=re.IGNORECASE), (
        "inline expiry must filter court_id, held, expires_at <= now() and interval overlap"
    )
    assert "cleanup only" in doc.lower(), "sweeper must be cleanup only"
    damaged = re.sub(r"cleanup only", "main sweeper", doc, flags=re.IGNORECASE)
    errors = doc_rules.check_document(damaged)
    assert any("cleanup only" in error for error in errors), errors


def test_spec_checker_detects_removed_inline_expiry() -> None:
    damaged = re.sub(r"inline expiry", "removed", _doc(), flags=re.IGNORECASE)
    errors = doc_rules.check_document(damaged)
    assert any("inline expiry" in error for error in errors), errors


def test_spec_hot_court_unstable_rho_and_no_transaction_lock() -> None:
    doc = _doc()
    # The spot-check and Round-2 records quote old findings verbatim; check the design itself.
    lowered = doc.split("## Spot-check record", 1)[0].lower()
    assert "4 ms critical section" not in lowered, "old 4 ms critical section claim survives"
    assert "150*0.010=1.5" in _compact(doc), "naive transaction-lock rho must be shown"
    assert "unstable" in lowered, "rho 1.5 must be labelled unstable"
    assert "no advisory lock" in lowered, "transaction-long advisory lock must be removed"


def test_spec_checker_rejects_old_4ms_critical_section() -> None:
    damaged = _doc().replace(
        "### Sizing arithmetic", "### Sizing arithmetic\n\n4 ms critical section\n"
    )
    errors = doc_rules.check_document(damaged)
    assert any("4 ms critical section" in error for error in errors), errors


def test_spec_checker_requires_hot_court_rho() -> None:
    damaged = re.sub(r"150\s*[×*]\s*0\.010\s*=\s*1\.5", "rho removed", _doc())
    errors = doc_rules.check_document(damaged)
    assert any("rho" in error or "1.5" in error for error in errors), errors


def test_spec_redis_set_nx_gate_fast_fail() -> None:
    lowered = _doc().lower()
    assert "set nx" in lowered, "fast-fail gate must use Redis SET NX"
    assert "1-2 ms" in lowered, "rejected requests must cost 1-2 ms"
    assert "fast-fail" in lowered or "fast fail" in lowered
    assert "10 minute" in lowered, "gate TTL must match the hold duration"
    damaged = re.sub(r"SET NX", "GET", _doc(), flags=re.IGNORECASE)
    errors = doc_rules.check_document(damaged)
    assert any("SET NX" in error for error in errors), errors


def test_spec_hot_cache_single_flight_stale_while_revalidate() -> None:
    lowered = _doc().lower()
    assert "single-flight" in lowered, "hot cache needs a single-flight refresh"
    assert "stale-while-revalidate" in lowered
    assert "1-2 s" in lowered, "hot cache TTL must be 1-2 s"


def test_spec_checker_requires_single_flight_cache() -> None:
    damaged = re.sub(r"single-flight", "plain", _doc(), flags=re.IGNORECASE)
    errors = doc_rules.check_document(damaged)
    assert any("single-flight" in error for error in errors), errors


def test_spec_cache_hit_rate_alert_per_non_hot_court() -> None:
    alerts = _section(_doc(), "## Indicators and alerts").lower()
    assert "non-hot" in alerts, "hit-rate alert must be scoped to non-hot courts"
    assert "hit rate" in alerts


def test_spec_checker_requires_non_hot_hit_rate_alert() -> None:
    damaged = re.sub(r"non-hot", "every court", _doc(), flags=re.IGNORECASE)
    errors = doc_rules.check_document(damaged)
    assert any("non-hot" in error for error in errors), errors


def test_spec_late_payment_callback_validation_and_dedupe() -> None:
    lowered = _doc().lower()
    for token in (
        "signature check",
        "amount-vs-reservation",
        "callback_event",
        "settlement file",
        "dedupe",
    ):
        assert token in lowered, f"missing late-payment control: {token}"


def test_spec_checker_requires_callback_validation() -> None:
    damaged = _doc().replace("signature check", "unchecked")
    errors = doc_rules.check_document(damaged)
    assert any("signature check" in error for error in errors), errors


def test_spec_late_payment_free_interval_branch() -> None:
    walkthrough = _section(_doc(), "## Late-payment walkthrough").lower()
    assert "still free" in walkthrough, "late payment while the interval is still free"
    assert "re-confirm" in walkthrough, "re-confirm policy must be documented"
    assert "default" in walkthrough, "refund must be the stated default"


def test_spec_checker_requires_free_interval_branch() -> None:
    damaged = _doc().replace("still free", "occupied")
    errors = doc_rules.check_document(damaged)
    assert any("still free" in error for error in errors), errors


def test_spec_assumptions_confirmed_means_captured() -> None:
    assumptions = _section(_doc(), "## Assumptions").lower()
    assert "confirmed" in assumptions and "captured" in assumptions


def test_spec_checker_requires_confirmed_captured_interpretation() -> None:
    damaged = _doc().replace("captured", "authorised")
    errors = doc_rules.check_document(damaged)
    assert any("captured" in error for error in errors), errors


def test_spec_erd_user_role_membership_report_tables() -> None:
    erd = _diagram(_doc(), "erDiagram")
    for entity in ("USER", "ROLE", "BRANCH_MEMBERSHIP", "REPORT_AGGREGATE"):
        assert entity in erd, f"ERD missing entity: {entity}"
    assert "role" in _entity(erd, "USER").lower(), "USER must carry a role"
    assert "refreshed_at" in _entity(erd, "REPORT_AGGREGATE").lower()
    for parent, child in (
        ("ROLE", "USER"),
        ("BRANCH", "BRANCH_MEMBERSHIP"),
        ("USER", "BRANCH_MEMBERSHIP"),
        ("BRANCH", "REPORT_AGGREGATE"),
    ):
        assert re.search(rf"{parent}\s+\|\|--o\{{\s+{child}\b", erd), (
            f"ERD missing relation {parent} 1:N {child}"
        )


def test_spec_checker_requires_auth_and_report_entities() -> None:
    damaged = _doc().replace("BRANCH_MEMBERSHIP", "MEMBERSHIP_REMOVED")
    errors = doc_rules.check_document(damaged)
    assert any("BRANCH_MEMBERSHIP" in error for error in errors), errors


def test_spec_no_unpartial_overlap_wording() -> None:
    # The spot-check and Round-2 records quote old wording verbatim; check the design itself.
    lowered = _doc().split("## Spot-check record", 1)[0].lower()
    assert "unpartial overlap" not in lowered, "awkward 'unpartial overlap' wording survives"
    assert "never overlap" in lowered


def test_spec_checker_rejects_unpartial_overlap_wording() -> None:
    damaged = _doc().replace("never overlap", "unpartial overlap")
    errors = doc_rules.check_document(damaged)
    assert any("unpartial overlap" in error for error in errors), errors


def test_spec_structure_check_only_note() -> None:
    assert "structure check" in _doc().lower(), "doc tests must be labelled structure checks"
    damaged = re.sub(r"structure check", "doc check", _doc(), flags=re.IGNORECASE)
    errors = doc_rules.check_document(damaged)
    assert any("structure check" in error for error in errors), errors


def test_spec_on_conflict_do_nothing_verified_for_exclusion_constraint() -> None:
    lowered = _doc().lower()
    assert "on conflict do nothing" in lowered
    assert "postgresql 16" in lowered or "pg16" in lowered
    assert "23p01" in lowered, "deferrable fallback must catch SQLSTATE 23P01"
    damaged = _doc().replace("23P01", "99999")
    errors = doc_rules.check_document(damaged)
    assert any("23P01" in error for error in errors), errors
