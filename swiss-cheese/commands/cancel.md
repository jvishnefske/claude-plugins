---
description: Cancel the current verification loop
---

You are canceling the current Swiss Cheese verification loop.

## Cancellation Process

To cancel orchestration, you have two options:

### Option 1: Rename/Remove Design Document

```bash
mv design.toml design.toml.disabled
```

Without a valid design document, the Stop hook will allow the session to end.

### Option 2: Force Exit

The orchestrator only blocks on Stop events. If you simply need to pause:
1. Note the current layer and progress
2. The status in `/tmp/swiss_cheese_<hash>.json` is preserved
3. Resuming later will continue from the same point

## Current Status

Before canceling, check current progress:

```bash
# Run each gate to see status
make validate-requirements
make validate-architecture
make validate-tdd
make validate-implementation
```

## Output Format

Report the cancellation status:

```
Swiss Cheese Loop Cancelled
===========================

Current Layer: <layer_name>

Gates Passed:
[x] requirements
[x] architecture
[ ] tdd
[ ] implementation
...

To resume later:
1. Ensure design.toml exists
2. Run /swiss-cheese:loop

To start fresh:
1. Delete design.toml
2. Create new design document
3. Run /swiss-cheese
```

## Notes

- Status file in `/tmp` is preserved for resumption
- No cleanup of worktrees or branches occurs
- Progress can be resumed by simply continuing work
