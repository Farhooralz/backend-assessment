---
description: Behaviour-preserving cleanup while all tests stay green
agent: build
---
 
Refactor the code for: $ARGUMENTS
 
Rules:
- Behaviour must not change. All tests must stay green; run them before and after.
- Never edit anything under `tests/`.
- Goals: smaller functions and modules, clearer names, remove dead code and duplication, add missing type hints and docstrings that explain *why*. Do not add features or dependencies.
- Show a short before/after summary and paste the real test and lint output.
 
