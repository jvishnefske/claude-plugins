---
description: Show current verification status across all layers
---

Display the current Swiss Cheese orchestration status.

## Check Status

The orchestrator tracks status in `/tmp/swiss_cheese_<hash>.json`. You don't have direct access to this file, but you can infer status from:

1. **Design document validation**: Check if `design.toml` exists and is valid TOML
2. **Gate validation**: Run Makefile targets to check each gate
3. **Test results**: Check for test output files

## Manual Gate Checks

Run individual gate targets to see their status:

```bash
# Check which gates pass
make validate-requirements
make validate-architecture
make validate-tdd
make validate-implementation
make validate-static-analysis
make validate-dynamic-analysis
make validate-review
make validate-safety-case
```

## Status Display Format

When reporting status, use this format:

```
Swiss Cheese Verification Status
================================

Design Document: design.toml (valid/invalid/missing)

Gate Status:
[x] Layer 1: Requirements     - PASSED
[x] Layer 2: Architecture     - PASSED
[x] Layer 3: TDD              - PASSED
[ ] Layer 4: Implementation   - IN PROGRESS  <-- Current
[ ] Layer 5: Static Analysis  - PENDING
[ ] Layer 6: Formal Verify    - PENDING (optional)
[ ] Layer 7: Dynamic Analysis - PENDING
[ ] Layer 8: Review           - PENDING
[ ] Layer 9: Safety Case      - PENDING

Current Layer Tasks:
- [ ] implement_core: Implement core functionality
- [ ] implement_integrations: Implement integration points

Traceability:
- Requirements defined: 5
- Requirements with tests: 3
- Requirements verified: 2
```

## Instructions

1. Check if `design.toml` exists and parse it for task information
2. Run `make validate-<layer>` for each layer to determine status
3. Read any test result files for traceability info
4. Display a summary in the format above

## Next Steps

Based on status:
- If gates failing: "Fix the issues reported by the failing gate"
- If tasks pending: "Complete the pending tasks for the current layer"
- If all passed: "All verification complete! Ready for release."
