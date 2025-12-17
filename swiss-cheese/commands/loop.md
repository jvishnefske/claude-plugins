---
description: Start iterative refinement loop until all gates pass
---

You are continuing the Swiss Cheese orchestrated execution loop.

## How the Loop Works

The orchestrator runs automatically on **Stop events**:

1. When you try to stop, the orchestrator intercepts
2. It checks the current layer's gate status
3. Runs `make validate-<layer>` to verify
4. If gate fails → blocks and prompts you to fix issues
5. If gate passes → advances to next layer
6. Loop continues until all 9 layers pass

## Your Role

Simply work on the current layer's tasks. The orchestrator will:
- Tell you which layer you're on
- Show any gate failures that need fixing
- Advance you automatically when gates pass

## Layer Progression

```
requirements → architecture → tdd → implementation →
static_analysis → formal_verification → dynamic_analysis →
review → safety
```

Each layer must pass its Makefile gate before advancing.

## Gate Validation

Gates are Makefile targets that return 0 for pass, non-zero for fail:

| Layer | Target | What it checks |
|-------|--------|----------------|
| requirements | `validate-requirements` | design.toml valid, all reqs have criteria |
| architecture | `validate-architecture` | Docs exist, Cargo.toml valid |
| tdd | `validate-tdd` | Tests compile |
| implementation | `validate-implementation` | Tests pass |
| static_analysis | `validate-static-analysis` | Clippy, audit, deny pass |
| formal_verification | `validate-formal-verification` | Kani passes (optional) |
| dynamic_analysis | `validate-dynamic-analysis` | Miri, coverage pass |
| review | `validate-review` | Review docs exist |
| safety | `validate-safety-case` | All evidence assembled |

## Instructions

1. Read the design document to understand current tasks
2. Work on tasks for the current layer
3. When ready, the orchestrator will validate the gate
4. Fix any failures reported
5. Continue until all gates pass

## Completion

When all gates pass:
- Traceability matrix saved to `.claude/traceability_matrix.json`
- Session completes successfully
- Ready for release decision

## Cancellation

To cancel the loop and stop immediately:
- Use `/swiss-cheese:cancel`
- Or remove/rename the design.toml file
