"""Fail fast when the Task 10 design document is missing a required deliverable."""

from __future__ import annotations

import argparse
from pathlib import Path

from doc_rules import check_document


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
