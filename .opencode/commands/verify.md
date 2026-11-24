---
description: Implement a task until its given tests pass (TDD green)
agent: build
---
 
Task to implement: $ARGUMENTS
 
Follow AGENTS.md strictly. Do this, in order:
 
1. Read the matching section of `docs/TEST_SPEC.md` and every file in that task's `tests/` folder. Tests define the names, signatures and behaviour you must provide.
2. Run the tests and show that they fail for the right reason (red).
3. Write the smallest code that makes the next failing test pass. Re-run the whole suite after every change.
4. NEVER edit, delete, skip or weaken anything under `tests/`. If a test looks wrong, stop and explain.
5. When everything is green, run the quality gate from AGENTS.md and paste the real output.
6. Report: files changed, the exact commands you ran with their real output, assumptions you made, and anything unfinished. Do not run git commit or git push.
7. (Rule 10) Verify red-first proof: every fix has a test that failed on the current code for the stated reason; the failing assertion line is pasted under "Round 2". A non-reproducing finding is recorded as "not reproduced" with evidence, not forced into a fix.
8. (Rule 11) Verify mutation checks hit business logic and name the exact `file::test_name` that fails; reject mutations of `ensure_db`, benchmark selectors, READMEs or type hints.
9. (Rule 12) Reject grep-as-proof and tautological/duplicate tests; every deliverable needs a behavioural test.
10. (Rule 13) Reproduce every README number; test counts must come from `pytest --collect-only -q | tail -1`.
11. (Rule 14) Atomicity/rollback tests use `transaction=True`, fail after the first write, and check state through a separate connection.
12. (Rule 15) Concurrency tests open the DB connection before the barrier, keep connections open through PID assertions, and use real processes where the spec says "workers".
13. (Rule 16) Check that docs and behaviour agree and that spec ambiguities are marked ⚠ under Assumptions.
Current git state:
!`git status --short`
 
