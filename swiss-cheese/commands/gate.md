---
description: "Gate to run: requirements, architecture, tdd, implementation, static-analysis, formal-verification, dynamic-analysis, review, safety-case"
arguments:
  - name: gate_name
    description: "Gate to run: requirements, architecture, tdd, implementation, static-analysis, formal-verification, dynamic-analysis, review, safety-case"
    required: true
---

You are manually running the **{{gate_name}}** verification gate.

## Running the Gate

Execute the Makefile target for this gate:

```bash
make validate-{{gate_name}}
```

## Gate Details

{{#if (eq gate_name "requirements")}}
### Layer 1: Requirements Validation

**Makefile Target**: `validate-requirements`

**What it checks**:
- `design.toml` exists and is valid TOML
- All requirements have `acceptance_criteria`
- Requirement IDs follow REQ-NNN pattern

**To pass manually**:
1. Ensure `design.toml` exists with valid [[requirements]] section
2. Each requirement needs: id, title, description, acceptance_criteria

{{else if (eq gate_name "architecture")}}
### Layer 2: Architecture Design

**Makefile Target**: `validate-architecture`

**What it checks**:
- Architecture documentation exists (docs/architecture.md or ARCHITECTURE.md)
- Cargo.toml is valid (if Rust project)

**To pass manually**:
1. Create architecture documentation
2. Ensure Cargo.toml structure is valid

{{else if (eq gate_name "tdd")}}
### Layer 3: Test-Driven Development

**Makefile Target**: `validate-tdd`

**What it checks**:
- Test files exist
- Tests compile (`cargo test --no-run`)

**To pass manually**:
1. Write tests for all requirements
2. Tests should compile but may fail (TDD red phase)

{{else if (eq gate_name "implementation")}}
### Layer 4: Implementation

**Makefile Target**: `validate-implementation`

**What it checks**:
- `cargo build --all-targets` succeeds
- `cargo test --all-features` passes

**To pass manually**:
1. Implement code to pass all tests
2. No build errors or warnings

{{else if (eq gate_name "static-analysis")}}
### Layer 5: Static Analysis

**Makefile Target**: `validate-static-analysis`

**What it checks**:
- `cargo clippy -- -D warnings` passes
- `cargo audit` (if installed) - no critical vulnerabilities
- `cargo deny check` (if configured) - license compliance

**To pass manually**:
1. Fix all Clippy warnings
2. Address any security advisories
3. Ensure license compliance

{{else if (eq gate_name "formal-verification")}}
### Layer 6: Formal Verification (Optional)

**Makefile Target**: `validate-formal-verification`

**What it checks**:
- `cargo kani` passes (if Kani installed)

**This layer is optional**. Skip with justification if:
- No unsafe code
- No critical invariants
- Kani not available

{{else if (eq gate_name "dynamic-analysis")}}
### Layer 7: Dynamic Analysis

**Makefile Target**: `validate-dynamic-analysis`

**What it checks**:
- `cargo +nightly miri test` (if available)
- `cargo llvm-cov` coverage >= threshold

**To pass manually**:
1. Run Miri to check for undefined behavior
2. Achieve coverage target (typically 70-80%)

{{else if (eq gate_name "review")}}
### Layer 8: Code Review

**Makefile Target**: `validate-review`

**What it checks**:
- Review documentation exists (REVIEW.md or .claude/review.md)

**To pass manually**:
1. Conduct code review
2. Document findings and resolutions

{{else if (eq gate_name "safety-case")}}
### Layer 9: Safety Case

**Makefile Target**: `validate-safety-case`

**What it checks**:
- All previous gates passed
- Traceability report generated

**To pass manually**:
1. Verify all evidence assembled
2. Make release decision
3. Traceability matrix complete

{{else}}
### Unknown Gate: {{gate_name}}

Valid gates are:
- requirements
- architecture
- tdd
- implementation
- static-analysis
- formal-verification
- dynamic-analysis
- review
- safety-case

{{/if}}

## Instructions

1. Run `make validate-{{gate_name}}`
2. If it fails, review the output and fix issues
3. Re-run until the gate passes
4. The orchestrator will automatically advance when the gate passes

## Exit Codes

- **0**: Gate passed
- **Non-zero**: Gate failed (see output for details)
