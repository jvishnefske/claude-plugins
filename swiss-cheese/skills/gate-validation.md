---
description: Use this skill when the user needs guidance on implementing gate validation, understanding exit codes, gate criteria by layer, or failure analysis and routing.
---

# Gate Validation Skill

This skill provides guidance on implementing and validating verification gates using Makefile targets.

## Exit Code Standard

| Code | Meaning | Action |
|------|---------|--------|
| 0 | PASS | Advance to next layer |
| Non-zero | FAIL | Fix issues and retry |

## Gate Implementation

Each gate is a Makefile target that:

1. Checks prerequisites
2. Runs validation checks
3. Returns appropriate exit code
4. Outputs diagnostic information

### Makefile Target Template

```makefile
validate-<layer>:
	@echo "=== Validating <Layer> ==="
	@# Check prerequisites
	@test -f design.toml || (echo "ERROR: design.toml not found" && exit 1)
	@# Run validation
	@<validation-command> || exit 1
	@echo "<Layer> validation passed"
```

## Gate Criteria by Layer

### Gate 1: Requirements (`validate-requirements`)

```yaml
criteria:
  - design.toml exists and is valid TOML
  - all requirements have unique IDs (REQ-NNN)
  - all requirements have acceptance_criteria
  - safety requirements identified
```

### Gate 2: Architecture (`validate-architecture`)

```yaml
criteria:
  - architecture documentation exists
  - Cargo.toml is valid (if Rust project)
  - module structure defined
  - ownership model documented
```

### Gate 3: TDD Tests (`validate-tdd`)

```yaml
criteria:
  - test files exist
  - tests compile (cargo test --no-run)
  - coverage plan defined
  - requirements traced to tests
```

### Gate 4: Implementation (`validate-implementation`)

```yaml
criteria:
  - cargo build succeeds
  - cargo test passes
  - no TODO/FIXME/unimplemented!
  - no_std compliant (if required)
```

### Gate 5: Static Analysis (`validate-static-analysis`)

```yaml
criteria:
  - clippy clean (no deny-level violations)
  - cargo audit clean (no vulnerabilities)
  - cargo deny clean (license compliance)
  - unsafe blocks justified and documented
```

### Gate 6: Formal Verification (`validate-formal-verification`)

```yaml
criteria:
  - Kani proofs pass (if available)
  - critical properties verified
  - assumptions documented
  - OR: layer skipped with justification
```

### Gate 7: Dynamic Analysis (`validate-dynamic-analysis`)

```yaml
criteria:
  - Miri finds no undefined behavior
  - coverage targets met (typically 70-80%)
  - fuzzing clean (no crashes)
```

### Gate 8: Review (`validate-review`)

```yaml
criteria:
  - independent review conducted
  - review documentation exists
  - no critical findings open
```

### Gate 9: Safety Case (`validate-safety-case`)

```yaml
criteria:
  - all previous gates passed
  - traceability matrix complete
  - evidence chain documented
  - release decision recorded
```

## Failure Analysis

When a gate fails, analyze root cause:

| Gate | Symptom | Root Cause | Route To |
|------|---------|------------|----------|
| 5 | clippy::unwrap_used | Implementation issue | Layer 4 |
| 5 | cargo-audit vuln | Dependency issue | Layer 5 |
| 7 | Miri UB | Unsafe implementation | Layer 4 |
| 7 | Low coverage | Missing tests | Layer 3 |
| 7 | Timing violation | Slow implementation | Layer 4 |

## Recording Results

Gate results are tracked in `/tmp/swiss_cheese_<hash>.json` by the orchestrator.

The traceability report is generated to `.claude/traceability_matrix.json`:

```json
{
  "requirements": [
    {
      "id": "REQ-001",
      "title": "Requirement title",
      "tests": ["test_req_001_case1", "test_req_001_case2"],
      "covered": true
    }
  ],
  "coverage": {
    "REQ-001": "verified"
  }
}
```

## Integration with Orchestrator

The orchestrator runs gates automatically on Stop events:

```
Stop Event → orchestrate.py → make validate-<layer> →
  Pass (exit 0) → Advance to next layer
  Fail (exit 1) → Block and prompt to fix
```
