"""Technical rules that the Task 10 design document must satisfy."""

from __future__ import annotations

import re

from round2_rules import check_round2

REQUIRED_SECTIONS: tuple[str, ...] = (
    "## Assumptions",
    "## API boundary",
    "## ERD",
    "## Sequence diagram",
    "## Late-payment walkthrough",
    "## Capacity model",
    "## SLO",
    "## Indicators and alerts",
    "## Recovery plan",
    "## Load test plan",
    "## Decisions and limitations",
    "## Run and test commands",
    "## Unfinished parts",
    "## Spot-check record",
    "## Round 2",
)

REQUIRED_TOKENS: tuple[str, ...] = (
    "80 branches",
    "court reservation",
    "online payment",
    "financial reporting",
    "300",
    "3000",
    "150",
    "10 minute",
    "5 minute",
    "p95",
    "250 ms",
    "tstzrange",
    "exclude",
    "idempotent",
    "provider reference",
    "refund",
    "reconciliation entry",
    "branch manager",
    "central finance",
    "aggregate",
    "redis",
    "ttl",
    "invalidat",
    "per-court",
    "serializ",
    "hot court",
    "read replica",
    "decision 1",
    "decision 2",
    "cost",
    "limitation",
    "implementation is not required",
    "pip install -r requirements.txt",
    "python check_doc.py",
    "python -m pytest -q",
    "inline expiry",
    "cleanup only",
    "set nx",
    "fast-fail",
    "1-2 ms",
    "1-2 s",
    "single-flight",
    "stale-while-revalidate",
    "non-hot",
    "signature check",
    "amount-vs-reservation",
    "callback_event",
    "settlement file",
    "dedupe",
    "still free",
    "re-confirm",
    "captured",
    "never overlap",
    "structure check",
    "on conflict do nothing",
    "postgresql 16",
    "23p01",
)

PARTIAL_EXCLUSION_SQL = (
    r"EXCLUDE\s+USING\s+gist\s*\(\s*court_id\s+WITH\s+=,\s*"
    r"reserved_interval\s+WITH\s+&&\s*\)\s*WHERE\s+status\s+IN\s*"
    r"\(\s*'held'\s*,\s*'confirmed'\s*\)"
)


def _compact(text: str) -> str:
    """Normalize multiplication signs and whitespace so equations can be matched."""
    return re.sub(r"\s+", "", text.replace("×", "*").replace("·", "*"))


def _section(text: str, heading: str) -> str:
    """Return the body of one `##` section."""
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


def _entity(erd: str, name: str) -> str:
    """Return the attribute body of one Mermaid ERD entity."""
    match = re.search(rf"\b{name}\s*\{{(.*?)\}}", erd, flags=re.DOTALL)
    return match.group(1) if match else ""


def check_document(text: str) -> list[str]:
    """Return every unmet spec requirement so CI can report them all at once."""
    errors: list[str] = []
    headings = {line.strip() for line in text.splitlines() if line.startswith("## ")}
    for heading in REQUIRED_SECTIONS:
        if heading not in headings:
            errors.append(f"missing section: {heading}")

    blocks = re.findall(r"```mermaid\s*\n(.*?)```", text, flags=re.DOTALL)
    for diagram, marker in (("erDiagram", "erDiagram"), ("sequenceDiagram", "sequenceDiagram")):
        if not any(diagram in block for block in blocks):
            errors.append(f"missing Mermaid {marker}")
    erd = next((block for block in blocks if "erDiagram" in block), "")
    sequence = next((block for block in blocks if "sequenceDiagram" in block), "")

    lowered = text.lower()
    for token in REQUIRED_TOKENS:
        if token not in lowered:
            errors.append(f"missing required content: {token}")

    if not re.search(PARTIAL_EXCLUSION_SQL, text, flags=re.IGNORECASE):
        errors.append("missing partial EXCLUDE ... WHERE status IN ('held','confirmed')")
    if not re.search(
        r"CREATE\s+EXTENSION(?:\s+IF\s+NOT\s+EXISTS)?\s+btree_gist", text, flags=re.IGNORECASE
    ):
        errors.append("missing btree_gist extension needed by the GiST = operator")
    erd_text = _section(text, "## ERD").lower()
    if "without the where clause" not in erd_text or "impossible" not in erd_text:
        errors.append("missing explanation of why an unpartial constraint blocks customer B")

    if "reserved_interval" not in _entity(erd, "RESERVATION"):
        errors.append("ERD: RESERVATION must own reserved_interval")
    if "reserved_interval" in _entity(erd, "COURT"):
        errors.append("ERD: COURT must not own reserved_interval")
    payment = _entity(erd, "PAYMENT")
    if "provider_reference" in _entity(erd, "RESERVATION") or not re.search(
        r"text\s+provider_reference.*\buk\b", payment, flags=re.DOTALL | re.IGNORECASE
    ):
        errors.append("ERD: unique text provider_reference belongs to PAYMENT only")
    for child in ("PAYMENT", "PAYMENT_ATTEMPT", "CALLBACK_EVENT"):
        if not re.search(rf"RESERVATION\s+\|\|--o\{{\s+{child}\b", erd):
            errors.append(f"ERD: RESERVATION to {child} must be 1:N")
    if re.search(r"RESERVATION\s+\|\|--o\|\s+PAYMENT\b", erd):
        errors.append("ERD: payments must be 1:N, not 1:0..1")

    notes = re.findall(r"Note over[^\n]*", sequence)
    complete = [
        note
        for note in notes
        if all(field in note.lower() for field in ("status", "money", "message", "reconcil"))
    ]
    if len(complete) < 7:
        errors.append("sequence diagram needs 7 notes with status/money/message/reconciliation")

    freshness = (
        _section(text, "## Capacity model")
        + _section(text, "## SLO")
        + _section(text, "## Decisions and limitations")
    ).lower()
    if "exceed 5 minutes" not in freshness and "exceeds 5 minutes" not in freshness:
        errors.append("missing statement that a replica-lagged view can exceed 5 minutes")
    if "2min+3min=5min" not in _compact(freshness) or "replica lag" not in freshness:
        errors.append("missing staleness budget: refresh interval + replica lag ≤ 5 min")
    if "primary" not in freshness or "timestamp" not in freshness:
        errors.append("missing primary-refresh alternative that bounds staleness")

    slo = _section(text, "## SLO")
    rows = [
        line
        for line in slo.splitlines()
        if line.startswith("|")
        and not re.match(r"\|\s*-", line)
        and "objective" not in line.lower()
    ]
    if len(rows) < 4 or any(
        token not in slo.lower()
        for token in ("250 ms", "reservation commit", "callback", "staleness")
    ):
        errors.append("at least four SLOs required (availability, commit, callbacks, staleness)")

    # Round-2 rules: require "inline expiry", reject "4 ms critical section", state hot-court rho.
    errors.extend(check_round2(text, erd=erd))
    return errors
