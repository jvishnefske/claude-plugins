---
description: Use this skill when the user asks about "Swiss Cheese Model", "safety-critical Rust", "verification layers", "how to use swiss-cheese plugin", "rust verification workflow", "9-layer verification", "concurrent task orchestration", "topological sorting", "worktree orchestrator", or needs guidance on using the Swiss Cheese verification plugin for Rust development.
---

# Swiss Cheese Model - Safety-Critical Rust Development Guide

The Swiss Cheese Model plugin implements a 9-layer verification approach for safety-critical Rust development, inspired by NASA's Swiss Cheese Model for accident prevention. It features **concurrent task orchestration** using topological sorting and git worktrees for parallel execution.

## Core Concept

Like layers of Swiss cheese, each verification layer catches defects that slip through previous layers. No single layer is perfect, but together they provide defense in depth.

## Concurrent Task Orchestration

The orchestrator maximizes parallelism while respecting task dependencies:

1. **Topological Sorting**: Uses Python's `graphlib.TopologicalSorter` to identify tasks that can run concurrently
2. **Git Worktrees**: Each task executes in its own branch worktree for isolation
3. **Auto-Retry**: Failed tasks are automatically retried (configurable `max_iterations`)
4. **Validators**: Layer-specific validators run after each task to verify success
5. **Linear Rebase**: Completed branches are rebased in dependency order

## The 9 Verification Layers

### Layer 1: Requirements (`/swiss-cheese:gate requirements`)
- Formalize requirements with Rust-specific constraints
- Identify ownership, lifetime, and concurrency requirements
- Define testable acceptance criteria
- Agent: `requirements-agent`

### Layer 2: Architecture (`/swiss-cheese:gate architecture`)
- Design type-safe, ownership-correct architecture
- Define module structure and trait contracts
- Plan error handling strategy
- Agent: `architecture-agent`

### Layer 3: TDD (`/swiss-cheese:gate tdd`)
- Write comprehensive tests BEFORE implementation
- Unit tests, integration tests, property-based tests
- Tests should compile but fail (red phase)
- Agent: `tdd-agent`

### Layer 4: Implementation (`/swiss-cheese:gate implementation`)
- Implement safe Rust code to pass tests
- Minimize `unsafe` blocks
- Follow Rust idioms and API guidelines
- Agent: `implementation-agent`

### Layer 5: Static Analysis (`/swiss-cheese:gate static-analysis`)
- Run `cargo clippy -- -D warnings`
- Run `cargo audit` for vulnerabilities
- Run `cargo deny check` for licenses
- Audit all `unsafe` blocks
- Agent: `static-analysis-agent`

### Layer 6: Formal Verification (`/swiss-cheese:gate formal-verification`)
- Prove properties with Kani, Prusti, Creusot
- Model checking for critical functions
- Can be skipped if no unsafe code (use `/swiss-cheese:skip-layer`)
- Agent: `formal-verification-agent`

### Layer 7: Dynamic Analysis (`/swiss-cheese:gate dynamic-analysis`)
- Run Miri for undefined behavior detection
- Fuzzing with cargo-fuzz
- Coverage analysis (target >80%)
- Agent: `dynamic-analysis-agent`

### Layer 8: Review (`/swiss-cheese:gate review`)
- Independent fresh-eyes code review
- Security, correctness, reliability, maintainability
- Agent: `review-agent` (uses Opus model)

### Layer 9: Safety Case (`/swiss-cheese:gate safety-case`)
- Assemble all verification evidence
- Requirements traceability
- Make GO/NO-GO release decision
- Agent: `safety-agent` (uses Opus model)

## Quick Start Commands

```
/swiss-cheese              # Start a new verification session
/swiss-cheese:status       # Show current verification status
/swiss-cheese:gate <name>  # Run a specific gate
/swiss-cheese:loop         # Iterate until all gates pass
/swiss-cheese:skip-layer   # Skip a layer with justification
/swiss-cheese:cancel       # Cancel the current loop
```

## State Management

### Orchestrator State (`.claude/orchestrator_state.json`)

The orchestrator maintains detailed task state:
```json
{
  "tasks": {
    "implement_core": {
      "status": "running",
      "layer": "implementation",
      "iteration": 0,
      "branch": "swiss-cheese/implement_core",
      "worktree_path": ".worktrees/swiss-cheese-implement_core",
      "validation_errors": []
    }
  },
  "current_batch": ["implement_core", "run_clippy"],
  "completed_branches": ["swiss-cheese/write_tests"],
  "max_iterations": 5,
  "max_parallel": 4
}
```

### Legacy State (`/tmp/swiss_cheese_state.json`)

For backward compatibility with layer-based commands:
```json
{
  "layer": "current-layer",
  "files": ["modified/files.rs"],
  "gates_passed": ["requirements", "architecture"],
  "ci_runs": [{"command": "cargo test", "layer": "tdd"}],
  "project_dir": "/path/to/project"
}
```

## Hooks

The plugin includes hooks that:
- **SessionStart**: Initialize orchestrator from design document
- **UserPromptSubmit**: Dispatch ready tasks via topological sort
- **SubagentStop**: Validate completed tasks, retry failures
- **Pre-edit**: Warn about unsafe patterns, enforce layer constraints
- **Post-edit**: Track modified files, invalidate dependent gates
- **Pre-bash**: Track verification commands
- **Stop**: Check for incomplete tasks, suggest next steps

## Example Architecture Document (TOML)

See `examples/example_project.toml` for a complete design document. Key sections:

```toml
[project]
name = "my-project"
max_iterations = 5       # Auto-retry failed tasks
max_parallel_agents = 4  # Concurrent worktrees

[layers.implementation]
description = "Implement safe Rust code"
depends_on = ["tdd"]
validators = ["cargo_test", "cargo_build"]

[tasks.implement_core]
layer = "implementation"
description = "Implement core functionality"
depends_on = ["write_tests"]
agent = "implementation-agent"
# branch auto-generated: swiss-cheese/implement_core

[validators]
cargo_test = "cargo test"
cargo_build = "cargo build"

[worktree]
branch_prefix = "swiss-cheese"
cleanup_on_success = true
```

## Orchestrator CLI

```bash
# Initialize from design document
python3 orchestrator.py init design.toml

# Check current status
python3 orchestrator.py status

# Dispatch ready tasks (called by hooks)
python3 orchestrator.py dispatch

# Handle subagent completion (called by hooks)
python3 orchestrator.py on_subagent_complete

# Rebase completed branches
python3 orchestrator.py rebase

# Reset state
python3 orchestrator.py reset
```

## Best Practices

1. **Don't skip layers** unless absolutely necessary
2. **Document skip decisions** with clear justification
3. **Re-run affected gates** when code changes
4. **Use the loop command** for orchestrated execution
5. **Review all warnings** from hooks before proceeding
6. **Design task dependencies** to maximize parallelism
7. **Use validators** to automatically verify task completion
8. **Check orchestrator status** to monitor concurrent tasks
