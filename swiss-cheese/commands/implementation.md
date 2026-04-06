---
description: Begin TDD implementation from task specification
---

You are starting Test-Driven Development for tasks defined in `docs/plans/tasks.yaml`.

## TDD Workflow

For each task, follow the Red-Green-Refactor cycle:

### 1. RED: Write Failing Tests First

Before writing any implementation:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_req_001_acceptance_criterion() {
        // Test the acceptance criteria from tasks.yaml
        // This test MUST fail initially (no implementation exists)
    }
}
```

- One test per acceptance criterion
- Name tests `test_req_NNN_*` for traceability
- Run `cargo test` - confirm tests fail (red)

### 2. GREEN: Minimal Implementation

Write the minimum code to make tests pass:

```bash
cargo test           # Must pass
cargo build          # Must pass
cargo clippy -- -D warnings  # No warnings allowed
```

- Only add code that tests require
- No speculative features
- No unused code paths

### 3. REFACTOR: Remove Uncovered Code

With tests covering all requirements, aggressively refactor:

```bash
cargo llvm-cov --html  # Generate coverage report
```

- **Delete any uncovered code** - if tests don't need it, remove it
- Simplify implementations
- Extract common patterns
- Tests must still pass after refactoring

## Cargo Requirements

All cargo commands must pass without warnings:

```bash
cargo build --all-targets 2>&1 | grep -E "^warning:" && exit 1
cargo test --all-features
cargo clippy --all-targets -- -D warnings
cargo fmt --check
```

The `make verify` target enforces these.

## Task Cycle

### 1. Select Ready Task

Tasks are ready when `status: pending` and all `deps` are `complete`.

### 2. Mark In Progress

```yaml
- id: task-001
  status: in_progress
```

### 3. Read Specification

If task has `spec_file`, read it for detailed requirements.

### 4. TDD Cycle

```
RED    → Write failing test for acceptance criterion
GREEN  → Write minimal code to pass
REFACTOR → Remove uncovered code, simplify
```

Repeat for each acceptance criterion.

### 5. Verify

```bash
make verify  # Must pass: build, test, clippy, fmt
```

### 6. Mark Complete

```yaml
- id: task-001
  status: complete
```

## Coverage-Driven Refactoring

In the refactor step:

1. Run coverage: `cargo llvm-cov`
2. Identify uncovered lines
3. For each uncovered line, ask: "Is this required by any test?"
4. If no test requires it → **delete it**
5. If a test should require it → add a test first

This ensures:
- All code is justified by requirements
- Dead code is eliminated
- Implementation is minimal

## Verification Gate

The Stop hook blocks until `make verify` passes:
- `cargo build --all-targets` (no warnings)
- `cargo test --all-features` (all pass)
- `cargo clippy -- -D warnings` (no warnings)
- `cargo fmt --check` (formatted)

## Commands

- `/swiss-cheese:design` - Create task specification
- `/swiss-cheese:implementation` - Begin TDD implementation
