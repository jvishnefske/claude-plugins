---
description: Show current verification status across all layers
---

Display the current Swiss Cheese orchestration status by querying the orchestrator.

## Get Status

Run the orchestrator status command:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/orchestrator.py status
```

## Status Report Format

```
Swiss Cheese Orchestration Status
=================================

Design Document: design.toml
Status Counts:
  - pending: 5
  - running: 2
  - passed: 8
  - failed: 0

Tasks:
  [PASSED]  parse_requirements (requirements) - swiss-cheese/parse_requirements
  [PASSED]  formalize_constraints (requirements) - swiss-cheese/formalize_constraints
  [RUNNING] write_unit_tests (tdd) - swiss-cheese/write_unit_tests
  [RUNNING] write_property_tests (tdd) - swiss-cheese/write_property_tests  <- parallel
  [PENDING] implement_core (implementation) - waiting on tests
  ...

Current Batch (running concurrently):
  - write_unit_tests
  - write_property_tests

Completed Branches (ready for rebase):
  - swiss-cheese/parse_requirements
  - swiss-cheese/formalize_constraints

Next: Tasks will dispatch automatically when dependencies complete.
```

## Legacy Status

For backward compatibility, also check `/tmp/swiss_cheese_state.json` for layer-based status:

```
Verification Layers:
[x] Layer 1: Requirements     - PASSED
[x] Layer 2: Architecture     - PASSED
[x] Layer 3: TDD              - PASSED
[ ] Layer 4: Implementation   - PENDING  <-- Current
...
```

## Instructions

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/orchestrator.py status` for task-level status
2. Parse and display the JSON output in a readable format
3. Show which tasks are running concurrently
4. Identify tasks ready to run next (dependencies satisfied)
5. Show any validation errors from failed tasks

## Next Steps

Based on status, suggest:
- If tasks pending: "Tasks will dispatch automatically, or run `/swiss-cheese:loop`"
- If tasks failed: "Review validation errors and fix issues"
- If all passed: "Ready to rebase with `/swiss-cheese:rebase`"
