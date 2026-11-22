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
Commits that touched tests:
!`git log --oneline -- task*/tests`
 
Overall change summary:
!`git diff --stat HEAD`
 
