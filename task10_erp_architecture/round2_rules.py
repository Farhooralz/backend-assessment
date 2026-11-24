"""Round-2 review rules for the Task 10 design document."""

from __future__ import annotations

import re

INLINE_EXPIRY_SQL = (
    r"UPDATE\s+reservation\s+SET\s+status\s*=\s*'expired'"
    r"\s+WHERE\s+court_id\s*=\s*\?"
    r"\s+AND\s+status\s*=\s*'held'"
    r"\s+AND\s+expires_at\s*<=\s*now\(\)"
    r"\s+AND\s+reserved_interval\s+&&\s*\?"
)
SIZING_EQUATIONS: tuple[str, ...] = (
    "3000*0.25=750",
    "300*0.25=75",
    "150*0.010=1.5",
    "150*0.002=0.3",
    "0.3/(1-0.3)*2=0.86",
    "1/600=0.0017",
    "150*0.010/6=0.25",
    "300*0.01=3",
    "750/50=15",
)
CALLBACK_CONTROLS: tuple[str, ...] = (
    "signature check",
    "amount-vs-reservation",
    "callback_event",
    "settlement file",
    "dedupe",
)
ERD_LINKS: tuple[tuple[str, str], ...] = (
    ("ROLE", "USER"),
    ("BRANCH", "BRANCH_MEMBERSHIP"),
    ("USER", "BRANCH_MEMBERSHIP"),
    ("BRANCH", "REPORT_AGGREGATE"),
)


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


def _compact(text: str) -> str:
    """Normalize multiplication signs and whitespace so equations can be matched."""
    return re.sub(r"\s+", "", text.replace("×", "*").replace("·", "*"))


def check_round2(text: str, erd: str) -> list[str]:
    """Return the Round-2 design-flaw findings for the document."""
    errors: list[str] = []
    # The spot-check and Round-2 records quote old findings verbatim; check only the design.
    design = text.split("## Spot-check record", 1)[0]
    design_lower = design.lower()
    design_compact = _compact(design)

    if "4 ms critical section" in design_lower:
        errors.append("must not contain the outdated '4 ms critical section' claim")
    if "150*0.010=1.5" not in design_compact or "unstable" not in design_lower:
        errors.append("hot-court rho must be 150*0.010=1.5 and labelled unstable")
    if "no advisory lock" not in design_lower or "set nx" not in design_lower:
        errors.append("hot court needs a Redis SET NX gate, not a transaction-long advisory lock")
    if "1-2 ms" not in design_lower or "fast-fail" not in design_lower:
        errors.append("rejected hot-court requests must fast-fail in 1-2 ms")
    if "inline expiry" not in design_lower or not re.search(
        INLINE_EXPIRY_SQL, design, re.IGNORECASE
    ):
        errors.append("insert path needs inline expiry with expires_at <= now() AND interval &&")
    if "cleanup only" not in design_lower:
        errors.append("sweeper must be cleanup only after inline expiry")

    if "single-flight" not in design_lower or "stale-while-revalidate" not in design_lower:
        errors.append("hot cache needs single-flight stale-while-revalidate refresh")
    alerts = _section(design, "## Indicators and alerts").lower()
    if "non-hot" not in alerts or "hit rate" not in alerts:
        errors.append("cache hit-rate alert must be defined per non-hot court")

    late = (
        _section(design, "## Assumptions")
        + _section(design, "## API boundary")
        + _section(design, "## Late-payment walkthrough")
        + _section(design, "## Recovery plan")
    ).lower()
    for token in CALLBACK_CONTROLS:
        if token not in late:
            errors.append(f"late-payment callback needs {token}")
    if "still free" not in late or "re-confirm" not in late or "default" not in late:
        errors.append(
            "late payment while the interval is still free needs refund default or re-confirm"
        )
    assumptions = _section(design, "## Assumptions").lower()
    if "confirmed" not in assumptions or "captured" not in assumptions:
        errors.append("Assumptions must state confirmed = provider captured the money")

    if "unpartial overlap" in design_lower or "never overlap" not in design_lower:
        errors.append(
            "must not say 'unpartial overlap': active intervals of one court never overlap"
        )
    if "structure check" not in design_lower:
        errors.append("must note that document tests are structure checks only")
    if "on conflict do nothing" not in design_lower or "23p01" not in design_lower:
        errors.append("must verify ON CONFLICT DO NOTHING and the SQLSTATE 23P01 fallback")

    capacity = _compact(_section(design, "## Capacity model"))
    if not all(equation in capacity for equation in SIZING_EQUATIONS):
        errors.append("missing revised sizing arithmetic (rho, SET NX gate, winners only)")

    for entity in ("USER", "ROLE", "BRANCH_MEMBERSHIP", "REPORT_AGGREGATE"):
        if entity not in erd:
            errors.append(f"ERD missing {entity} table the API relies on")
    if "role" not in _entity(erd, "USER").lower():
        errors.append("ERD: USER must carry a role")
    if "refreshed_at" not in _entity(erd, "REPORT_AGGREGATE").lower():
        errors.append("ERD: REPORT_AGGREGATE must carry refreshed_at")
    for parent, child in ERD_LINKS:
        if not re.search(rf"{parent}\s+\|\|--o\{{\s+{child}\b", erd):
            errors.append(f"ERD missing relation {parent} 1:N {child}")
    return errors
