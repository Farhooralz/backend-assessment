#!/usr/bin/env python3
"""Apply three deliberate defects to a temp copy and report which tests catch them.

The real implementation is never edited: sources are copied to a temporary
directory, one defect is applied there, and pytest runs against that copy.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parent

DEFECTS: tuple[str, ...] = (
    "24h boundary uses > instead of >=",
    "half refund rounds up instead of down",
    "remove transaction.atomic() (and the row lock it requires)",
)

# name -> (exact source to find, replacement, test id expected to catch it)
MUTATIONS: dict[str, tuple[str, str, str]] = {
    DEFECTS[0]: (
        "if remaining >= FULL_REFUND_THRESHOLD:",
        "if remaining > FULL_REFUND_THRESHOLD:",
        "tests/test_integration.py::test_spec_exactly_24h_remaining_returns_101",
    ),
    DEFECTS[1]: (
        "return payment_amount // 2",
        "return -(-payment_amount // 2)",
        "tests/test_integration.py::test_spec_exactly_2h_remaining_returns_50",
    ),
    DEFECTS[2]: (
        "    with transaction.atomic():\n"
        "        # Lock first: a racing caller then sees the committed status and replays\n"
        "        # the stored result instead of writing a second refund document.\n"
        "        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)",
        "    if True:\n"
        "        # DEFECT: no transaction; Django forbids select_for_update() in autocommit.\n"
        "        locked = Reservation.objects.get(pk=reservation.pk)",
        "tests/test_failure.py::test_spec_document_write_failure_rolls_back",
    ),
}


def _load_env() -> None:
    """Export the shared env contract for the child pytest runs, without printing it."""
    env_path = TASK_ROOT.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _copy_sources(target: Path) -> None:
    """Copy the whole task into a temporary pytest project."""
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(TASK_ROOT / "cancelapp", target / "cancelapp", ignore=ignore)
    shutil.copytree(TASK_ROOT / "tests", target / "tests", ignore=ignore)
    shutil.copy(TASK_ROOT / "mutation_check.py", target / "mutation_check.py")
    (target / "pytest.ini").write_text(
        "[pytest]\n"
        "DJANGO_SETTINGS_MODULE = cancelapp.settings\n"
        "pythonpath = .\n"
        "testpaths = tests\n"
        "timeout = 30\n",
        encoding="utf-8",
    )


def _apply_defect(source: Path, name: str) -> None:
    """Replace one exact source fragment; fail loudly if the anchor moved."""
    old, new, _expected = MUTATIONS[name]
    text = source.read_text(encoding="utf-8")
    if old not in text:
        msg = f"mutation anchor not found for {name!r} in {source}"
        raise RuntimeError(msg)
    source.write_text(text.replace(old, new, 1), encoding="utf-8")


def _failed_names(output: str) -> list[str]:
    """Extract test ids from pytest's ``FAILED`` summary lines."""
    return [line.split()[1] for line in output.splitlines() if line.startswith("FAILED ")]


def _run_pytest(target: Path) -> list[str]:
    """Run the suite in the temporary copy and return the failing test ids."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
    )
    return _failed_names(completed.stdout)


def main() -> int:
    """Print a defect-to-test table and exit non-zero if a defect survived."""
    _load_env()
    print(f"{'deliberate defect':<55} | failing test ids")
    print("-" * 150)
    all_caught = True
    for name in DEFECTS:
        with tempfile.TemporaryDirectory(prefix="task09-mutation-") as tmp:
            target = Path(tmp)
            _copy_sources(target)
            _apply_defect(target / "cancelapp" / "services.py", name)
            failures = _run_pytest(target)
        expected = MUTATIONS[name][2]
        caught = expected in failures
        all_caught = all_caught and caught
        shown = ", ".join(failures) or "NO TEST FAILED"
        print(f"{name:<55} | {shown}")
        print(f"{'':<55} | expected {expected}: {'CAUGHT' if caught else 'MISSED'}")
    return 0 if all_caught else 1


if __name__ == "__main__":
    raise SystemExit(main())
