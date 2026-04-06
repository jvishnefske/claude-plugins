---
description: "Gate to run: requirements, tdd, implementation, verify"
arguments:
  - name: gate_name
    description: "Gate to run: requirements, tdd, implementation, verify"
    required: true
---

You are running the **{{gate_name}}** verification gate.

## Step 1: Scaffold Check

Before running the gate, verify that the project has the required infrastructure. Check for **all** of the following:

### 1a. Makefile with gate targets

Run:
```bash
test -f Makefile && make -n validate-{{gate_name}} 2>/dev/null
```

If the Makefile is missing or lacks the `validate-{{gate_name}}` target, **scaffold it now**.

### 1b. Report directory

```bash
test -d docs/plans
```

If missing, create it: `mkdir -p docs/plans`

### 1c. Design document (requirements gate only)

{{#if (eq gate_name "requirements")}}
If `design.toml` does not exist, scaffold a starter template (see below).
{{/if}}

---

## Scaffolding

If any infrastructure is missing, generate it before running the gate. **Do not ask the user** — scaffold, explain what was created, then proceed to run the gate.

### Scaffold: Makefile

Detect the project language from existing files:

| Signal | Language | Build tool |
|--------|----------|------------|
| `Cargo.toml` | Rust | cargo |
| `package.json` | Node/TS | npm/vitest/jest |
| `pyproject.toml` or `setup.py` | Python | pytest |
| `go.mod` | Go | go test |
| `Makefile` already exists | — | Append missing targets only |

Generate a Makefile with **all 4 gate targets** plus supporting infrastructure. Use the language-appropriate template below.

#### Rust Makefile

```makefile
# Swiss Cheese Verification Makefile
#
# Usage: make setup && make verify
# Reports: docs/plans/

.PHONY: all verify verify-quick clean help setup
.PHONY: validate-requirements validate-tdd validate-implementation validate-verify
.PHONY: build test clippy fmt coverage reports

# Configuration
COVERAGE_THRESHOLD ?= 70
REPORT_DIR ?= docs/plans

all: verify

# =============================================================================
# Setup
# =============================================================================
setup:
	@rustup component add rustfmt clippy 2>/dev/null || true
	@command -v cargo-llvm-cov >/dev/null || cargo install cargo-llvm-cov
	@command -v cargo-audit >/dev/null || cargo install cargo-audit
	@mkdir -p $(REPORT_DIR)
	@echo "✓ Setup complete"

# =============================================================================
# Gate Targets
# =============================================================================
validate-requirements:
	@echo "=== Layer 1: Requirements ==="
	@test -f design.toml || (echo "ERROR: design.toml not found" && exit 1)
	@python3 -c "import tomllib; d=tomllib.load(open('design.toml','rb')); \
		missing=[r['id'] for r in d.get('requirements',[]) if not r.get('acceptance_criteria')]; \
		exit(1) if missing else print('✓ Requirements valid')" || exit 1

validate-tdd:
	@echo "=== Layer 2: TDD ==="
	@cargo test --no-run 2>&1
	@echo "✓ Tests compile"

validate-implementation: build test
	@echo "✓ Layer 3: Implementation validated"

validate-verify: clippy fmt coverage
	@echo "✓ Layer 4: Verification complete"

# =============================================================================
# Verify (all gates)
# =============================================================================
verify: validate-requirements validate-tdd validate-implementation validate-verify
	@echo "✓ All verification passed"

verify-quick: clippy test
	@echo "✓ Quick verification passed"

# =============================================================================
# Build & Test
# =============================================================================
build:
	@cargo build --all-targets

test:
	@cargo test --all-features

# =============================================================================
# Static Analysis
# =============================================================================
clippy:
	@cargo clippy --all-targets --all-features -- -D warnings

fmt:
	@cargo fmt --check || (echo "Run 'cargo fmt' to fix" && exit 1)

audit:
	@command -v cargo-audit >/dev/null && cargo audit || echo "cargo-audit not installed"

# =============================================================================
# Coverage
# =============================================================================
coverage: $(REPORT_DIR)
	@command -v cargo-llvm-cov >/dev/null && \
		cargo llvm-cov --all-features --json --output-path $(REPORT_DIR)/coverage.json && \
		cargo llvm-cov report --fail-under-lines $(COVERAGE_THRESHOLD) || \
		echo "Coverage check skipped (install cargo-llvm-cov)"

# =============================================================================
# Reports
# =============================================================================
$(REPORT_DIR):
	@mkdir -p $(REPORT_DIR)

reports: $(REPORT_DIR)
	@echo "=== Generating Reports ==="
	@cargo test --all-features -- -Z unstable-options --format json 2>/dev/null > $(REPORT_DIR)/test-results.json || true
	@cargo clippy --all-targets --all-features --message-format=json 2>/dev/null > $(REPORT_DIR)/clippy-report.json || true
	@command -v cargo-llvm-cov >/dev/null && cargo llvm-cov --all-features --json --output-path $(REPORT_DIR)/coverage.json || true
	@echo "✓ Reports in $(REPORT_DIR)/"

# =============================================================================
# Utilities
# =============================================================================
clean:
	@rm -rf target $(REPORT_DIR)/*.json
	@echo "✓ Clean"

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Gates:   validate-requirements, validate-tdd, validate-implementation, validate-verify"
	@echo "Verify:  verify (all gates), verify-quick (clippy + test)"
	@echo "Reports: reports (JSON output to $(REPORT_DIR)/)"
	@echo "Tools:   clippy, fmt, audit, coverage"
	@echo ""
	@echo "Config: COVERAGE_THRESHOLD=$(COVERAGE_THRESHOLD) REPORT_DIR=$(REPORT_DIR)"
```

#### Node/TypeScript Makefile

```makefile
.PHONY: all verify validate-requirements validate-tdd validate-implementation validate-verify

COVERAGE_THRESHOLD ?= 70
REPORT_DIR ?= docs/plans

all: verify

validate-requirements:
	@test -f design.toml || (echo "ERROR: design.toml not found" && exit 1)
	@echo "✓ Requirements valid"

validate-tdd:
	@npx tsc --noEmit
	@echo "✓ Tests compile"

validate-implementation:
	@npm test
	@echo "✓ Implementation validated"

validate-verify:
	@npx eslint . || true
	@npm test -- --coverage --coverageThreshold='{"global":{"lines":$(COVERAGE_THRESHOLD)}}' 2>/dev/null || true
	@echo "✓ Verification complete"

verify: validate-requirements validate-tdd validate-implementation validate-verify
	@echo "✓ All verification passed"

$(REPORT_DIR):
	@mkdir -p $(REPORT_DIR)
```

#### Python Makefile

```makefile
.PHONY: all verify validate-requirements validate-tdd validate-implementation validate-verify

COVERAGE_THRESHOLD ?= 70
REPORT_DIR ?= docs/plans

all: verify

validate-requirements:
	@test -f design.toml || (echo "ERROR: design.toml not found" && exit 1)
	@echo "✓ Requirements valid"

validate-tdd:
	@python -m pytest --collect-only 2>&1 > /dev/null
	@echo "✓ Tests compile"

validate-implementation:
	@python -m pytest
	@echo "✓ Implementation validated"

validate-verify:
	@python -m pytest --cov --cov-fail-under=$(COVERAGE_THRESHOLD) || true
	@echo "✓ Verification complete"

verify: validate-requirements validate-tdd validate-implementation validate-verify
	@echo "✓ All verification passed"

$(REPORT_DIR):
	@mkdir -p $(REPORT_DIR)
```

#### Go Makefile

```makefile
.PHONY: all verify validate-requirements validate-tdd validate-implementation validate-verify

COVERAGE_THRESHOLD ?= 70
REPORT_DIR ?= docs/plans

all: verify

validate-requirements:
	@test -f design.toml || (echo "ERROR: design.toml not found" && exit 1)
	@echo "✓ Requirements valid"

validate-tdd:
	@go test -run xxx ./... 2>&1
	@echo "✓ Tests compile"

validate-implementation:
	@go test ./...
	@echo "✓ Implementation validated"

validate-verify:
	@go vet ./...
	@staticcheck ./... 2>/dev/null || true
	@go test -coverprofile=$(REPORT_DIR)/coverage.out ./... && \
		go tool cover -func=$(REPORT_DIR)/coverage.out || true
	@echo "✓ Verification complete"

verify: validate-requirements validate-tdd validate-implementation validate-verify
	@echo "✓ All verification passed"

$(REPORT_DIR):
	@mkdir -p $(REPORT_DIR)
```

### Scaffold: design.toml

{{#if (eq gate_name "requirements")}}
If `design.toml` is missing, create a starter:

```toml
[project]
name = ""  # Fill in project name
version = "0.1.0"

[[requirements]]
id = "REQ-001"
title = ""  # Fill in first requirement
description = ""
priority = "high"
acceptance_criteria = [
    "",  # Fill in testable criterion
]
```

Tell the user to fill in the placeholder fields.
{{/if}}

### Scaffold: Appending to existing Makefile

If a Makefile exists but is missing gate targets, **append** the missing `validate-*` targets rather than overwriting. Check each target individually:

```bash
make -n validate-requirements 2>/dev/null || echo "# missing: validate-requirements"
make -n validate-tdd 2>/dev/null || echo "# missing: validate-tdd"
make -n validate-implementation 2>/dev/null || echo "# missing: validate-implementation"
make -n validate-verify 2>/dev/null || echo "# missing: validate-verify"
```

Append only the missing targets using the language-appropriate template above.

---

## Step 2: Run the Gate

Execute the Makefile target:

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
- All requirements have unique IDs (REQ-NNN format)

{{else if (eq gate_name "tdd")}}
### Layer 2: TDD Tests

**Makefile Target**: `validate-tdd`

**What it checks**:
- Test files exist
- Tests compile (may fail at runtime — that's expected in red phase)

{{else if (eq gate_name "implementation")}}
### Layer 3: Implementation

**Makefile Target**: `validate-implementation`

**What it checks**:
- Project builds without errors
- All tests pass

{{else if (eq gate_name "verify")}}
### Layer 4: Verify

**Makefile Target**: `validate-verify`

**What it checks**:
- Static analysis passes (clippy for Rust, eslint for TS, etc.)
- Code is formatted
- Coverage meets threshold (default: 70%)

Report artifacts written to `docs/plans/`:
- `coverage.json` — llvm-cov / coverage output
- `clippy-report.json` — static analysis results
- `test-results.json` — test run output

{{else}}
### Unknown Gate: {{gate_name}}

Valid gates: `requirements`, `tdd`, `implementation`, `verify`

{{/if}}

## Step 3: Handle Results

- **Exit 0** → Gate passed. Report success.
- **Non-zero** → Gate failed. Show the output, diagnose the issue, and fix it. Re-run until the gate passes.

If the gate fails, analyze root cause:

| Gate | Common Failure | Fix |
|------|---------------|-----|
| requirements | Missing design.toml | Create it with `/swiss-cheese:design` |
| tdd | Tests don't compile | Fix test code |
| implementation | Tests fail | Fix implementation |
| verify | Clippy warnings / low coverage | Fix warnings, add tests |
