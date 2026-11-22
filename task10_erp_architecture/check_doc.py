"""Fail fast when the Task 10 design document is missing a required deliverable."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

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
)


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

    lowered = text.lower()
    for token in REQUIRED_TOKENS:
        if token not in lowered:
            errors.append(f"missing required content: {token}")
    return errors


def main() -> int:
    """Check the document given on the command line and exit non-zero on failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("README.md"),
        help="Markdown document to validate (defaults to README.md here)",
    )
    args = parser.parse_args()
    text = args.path.read_text(encoding="utf-8")
    errors = check_document(text)
    for error in errors:
        print(f"FAIL: {error}")
    if errors:
        print(f"{len(errors)} problem(s) found in {args.path}")
        return 1
    print(f"OK: {args.path} contains all required sections and diagrams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
