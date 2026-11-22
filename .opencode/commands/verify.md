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
Current git state:
!`git status --short`
 
