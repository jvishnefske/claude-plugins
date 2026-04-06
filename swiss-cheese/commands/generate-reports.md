---
description: Generate Swiss Cheese validation report by running all layer gates
---

# Generate Validation Report

This command runs all verification layer gates and generates a validation report at `.swiss-cheese/reports/validation_report.json`.

## What This Does

1. **Runs all 4 layer Makefile targets**:
   - `validate-requirements` (Layer 1)
   - `validate-tdd` (Layer 2)
   - `validate-implementation` (Layer 3)
   - `validate-verify` (Layer 4)

2. **Collects metrics** (if available):
   - Code coverage from `docs/plans/coverage.json`
   - Test results from `docs/plans/test-results.json`
   - Requirements traceability from `design.toml`

3. **Embeds git hash** for staleness detection

## Usage

Run this command when you want to:
- Update the validation report after making changes
- Generate a fresh report before starting development
- Check current gate status in detail

## Report Location

The report is written to: `.swiss-cheese/reports/validation_report.json`

## Execution

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/generate_reports.py --project-dir ${CLAUDE_PROJECT_DIR}
```
