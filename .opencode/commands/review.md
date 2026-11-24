---
description: Read-only review of a task against the spec; checks tests were not touched
agent: plan
---
 
Review the work for: $ARGUMENTS
 
Do not change any files. Check, and report as a short checklist with PASS/FAIL and evidence:
 
1. Every sample/acceptance line and every "constraints and deliverables" item in the task's section of `docs/TEST_SPEC.md` is satisfied. Quote the spec line next to the code or test that covers it.
2. The tests were NOT modified after they were added. Evidence: the commits that touched tests are listed below. More than one commit touching `tests/` is a red flag, so inspect it.
3. Correctness risks: edge cases, error handling, concurrency, security (secrets, authorization, logging of sensitive data).
4. Code quality: small modules, clear names, type hints, no dead code, no `float` for money.
5. README has: run command, test command, assumptions, unfinished parts, and the task-specific deliverables.
6. (Rule 10) **Red first, with proof.** Every fix has a test that failed on the current code for the stated reason; the failing assertion line is in the task README under "Round 2". Non-reproducing findings say "not reproduced" with evidence.
7. (Rule 11) **Mutation checks must hit business logic.** Each README mutation changes behaviour (filter, comparison, lock, `atomic()`, `distinct`) and names the exact catching `file::test_name`; infra selectors, READMEs and type hints do not count.
8. (Rule 12) **No grep-as-proof.** Source/README-grep tests are only extra deliverable checks; each deliverable also has a behavioural test. Tautological and duplicate tests are deleted.
9. (Rule 13) **Every number in a README must be reproducible.** Counts come from `pytest --collect-only -q | tail -1`; timings and claims are either reproducible or absent.
10. (Rule 14) **Atomicity/rollback tests** use `@pytest.mark.django_db(transaction=True)`, inject failure after the first write, and verify state through a separate connection.
11. (Rule 15) **Concurrency tests:** open the DB connection before the barrier; keep connections open until after PID assertions; use real processes where the spec says "workers" (threads only for DB row-lock races).
12. (Rule 16) **Honest docs.** Behaviour, README and docstrings agree; spec ambiguities are marked ⚠ under Assumptions.
Commits that touched tests:
!`git log --oneline -- task*/tests`
 
Overall change summary:
!`git diff --stat HEAD`
 
