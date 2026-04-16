# Swiss Cheese Plugin Design Specification

## Purpose

Claude Code plugin implementing the Swiss Cheese Model for iterative Rust development lifecycle with multi-layer defect escape reduction methodology.

## Architecture Overview

The plugin follows a **layered verification architecture** where each layer acts as a defect filter:

```
User Request
    |
    v
+-------------------+
| Orchestrator      | <-- Single coordination point
| Architect Agent   |
+-------------------+
    |
    v (9 layers, each with gate validation)
+-------------------+
| Layer 1-9         | --> Exit codes: 0=PASS, 1=FAIL, 2=BLOCKED, 3=SKIP
| Swiss Cheese      |
+-------------------+
    |
    v
Release Package
```

### Core Components

1. **Orchestrator Architect**: Single top-level agent coordinating all verification
2. **Gate Validators**: Exit code-based validation for each layer
3. **Iterative Loop (ralph-wiggum)**: Automatic retry until all gates pass
4. **Hooks**: Session lifecycle, subagent coordination, gate verification

### Data Flow

- Immutable state transformations via `state.json` and `loop-state.json`
- Artifact storage per layer in `.swiss-cheese/artifacts/`
- Design specification in `.swiss-cheese/design-spec.yaml`

## MVP Functional Requirements

### FR-001: Session State Management
- [x] **FR-001.1**: SessionStart hook loads existing state from `.swiss-cheese/state.json`
- [x] **FR-001.2**: SessionStart hook displays paused loop status if present
- [x] **FR-001.3**: State transitions are immutable (new JSON written, not mutated in place)

### FR-002: Task Specification Parsing
- [x] **FR-002.1**: Parse TOML task specifications with version validation
- [x] **FR-002.2**: Validate task dependencies reference existing tasks
- [x] **FR-002.3**: Detect dependency cycles via topological sort
- [x] **FR-002.4**: Return ready tasks (pending with all deps complete)

### ~~FR-003: Git Worktree Management~~ (DEPRECATED)
- ~~**FR-003.1**: Detect if current directory is a worktree~~ — removed, worktree orchestration out of scope
- ~~**FR-003.2**: Get worktree branch name from git~~ — removed, worktree orchestration out of scope
- [x] **FR-003.3**: Determine main branch (main or master fallback)
- [x] **FR-003.4**: Check if branch is in linear history of main

### FR-004: Gate Verification
- [x] **FR-004.1**: Run `make verify` in project directory
- [x] **FR-004.2**: Return success/failure with captured output
- [x] **FR-004.3**: Handle missing Makefile gracefully

### FR-005: Subagent Stop Coordination
- [ ] **FR-005.1**: SubagentStop hook detects task completion
- ~~**FR-005.2**: Hook triggers worktree cleanup when branch merged to main~~ — DEPRECATED, worktree orchestration out of scope
- [ ] **FR-005.3**: Hook updates task status in spec file

### FR-006: Loop Control
- [ ] **FR-006.1**: `/swiss-cheese:loop` starts iterative verification loop
- [ ] **FR-006.2**: Loop state persisted to `.swiss-cheese/loop-state.json`
- [ ] **FR-006.3**: Stop hook blocks exit during active loop
- [ ] **FR-006.4**: `/swiss-cheese:cancel` terminates active loop

### FR-007: Validation Reports
- [x] **FR-007.1**: Gate check hook reads `.swiss-cheese/reports/validation_report.json`
- [x] **FR-007.2**: Gate check compares report git hash vs current HEAD for staleness
- [x] **FR-007.3**: Gate check completes in <100ms (read-only, no subprocess)
- [x] **FR-007.4**: `/swiss-cheese:generate-reports` runs all layer gates
- [x] **FR-007.5**: Report includes layer status, coverage, tests, traceability metrics
- [x] **FR-007.6**: Report embeds git hash for staleness detection

## Test Coverage Requirements

| Component | Target Coverage |
|-----------|----------------|
| session_start.py | 80% |
| subagent_stop.py | 80% |
| verify_gate.py | 80% |
| Overall | 75% |

## Verification Traceability

| Requirement | Test File | Test Class/Method |
|-------------|-----------|-------------------|
| FR-002.1 | test_hooks.py | TestParseSpec.test_parse_valid_toml |
| FR-002.2 | test_hooks.py | TestTaskSpec.test_invalid_dep_reference_fails |
| FR-002.3 | test_hooks.py | TestTopologicalSort.test_cycle_detected |
| FR-002.4 | test_hooks.py | TestGetReadyTasks.* |
| ~~FR-003.1~~ | ~~test_hooks.py~~ | ~~DEPRECATED~~ |
| ~~FR-003.2~~ | ~~test_hooks.py~~ | ~~DEPRECATED~~ |
| FR-003.3 | test_hooks.py | TestSubagentStopHelpers.test_get_main_branch_* |
| FR-003.4 | test_hooks.py | TestSubagentStopHelpers.test_branch_*_history_* |
| FR-004.1 | test_hooks.py | TestVerifyGate.test_run_verify_success |
| FR-004.2 | test_hooks.py | TestVerifyGate.test_run_verify_failure |
| FR-004.3 | test_hooks.py | TestVerifyGate.test_run_verify_no_make |
| FR-001.1 | test_hooks.py | TestLoadSaveState.test_load_state_* |
| FR-001.2 | test_hooks.py | TestFormatLoopStatus.* |
| FR-001.3 | test_hooks.py | TestLoadSaveState.test_save_state_* |
| FR-007.1 | test_hooks.py | TestReadReport.* |
| FR-007.2 | test_hooks.py | TestCheckStaleness.* |
| FR-007.3 | test_hooks.py | TestMainReadOnly.* |
| FR-007.4 | test_generate_reports.py | TestRunLayerGates.* |
| FR-007.5 | test_generate_reports.py | TestCollectMetrics.* |
| FR-007.6 | test_generate_reports.py | TestGenerateReport.test_git_hash_embedded |
