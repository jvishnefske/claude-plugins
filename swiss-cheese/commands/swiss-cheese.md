---
description: Start safety-critical Rust development with design review
arguments:
  - name: design_doc
    description: Path to design document (TOML or markdown)
    required: false
---

You are starting a safety-critical Rust development session using the Swiss Cheese Model with **concurrent task orchestration**.

## Swiss Cheese Model Overview

Like the NASA Swiss Cheese Model for accident prevention, this workflow uses 9 independent verification layers. Each layer catches defects that slip through previous layers - no single point of failure.

```
Layer 1: Requirements    → Formalize requirements with Rust-specific constraints
Layer 2: Architecture    → Design type-safe, ownership-correct architecture
Layer 3: TDD             → Write comprehensive tests BEFORE implementation
Layer 4: Implementation  → Implement safe Rust code to pass tests
Layer 5: Static Analysis → Run Clippy, cargo-audit, cargo-deny, unsafe audit
Layer 6: Formal Verify   → Prove properties with Kani, Prusti, Creusot
Layer 7: Dynamic Analysis→ Run Miri, fuzzing, coverage, timing analysis
Layer 8: Review          → Independent fresh-eyes review
Layer 9: Safety Case     → Assemble safety case and make release decision
```

## Concurrent Task Orchestration

The orchestrator uses **topological sorting** to identify tasks that can run in parallel:
- Tasks with satisfied dependencies are dispatched concurrently
- Each task runs in its own **git worktree** branch
- Validators run after each task to verify success
- Failed tasks are automatically retried (up to max_iterations)
- Completed branches are rebased in dependency order

## Your Task

{{#if design_doc}}
1. Read and analyze the design document at: {{design_doc}}
2. Initialize the orchestrator with the design document
3. Display the task dependency graph
4. Begin orchestrated execution

**Initialize orchestrator:**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/orchestrator.py init "{{design_doc}}"
```
{{else}}
1. Look for existing design documents: `design.toml`, `requirements.toml`, `swiss-cheese.toml`
2. If none found, help the user create one (see `examples/example_project.toml`)
3. Initialize the orchestrator once a design document exists
{{/if}}

## Design Document Format (TOML)

The design document defines layers, tasks, validators, and orchestration settings:

```toml
[project]
name = "my-project"
max_iterations = 5          # Retry failed tasks
max_parallel_agents = 4     # Concurrent worktrees

[layers.implementation]
description = "Implement safe Rust code"
depends_on = ["tdd"]
validators = ["cargo_test", "cargo_build"]

[tasks.implement_core]
layer = "implementation"
description = "Implement core functionality"
depends_on = ["write_tests"]
agent = "implementation-agent"

[validators]
cargo_test = "cargo test"
cargo_build = "cargo build"

[worktree]
branch_prefix = "swiss-cheese"
cleanup_on_success = true
```

## Session State

The orchestrator maintains state in `.claude/orchestrator_state.json`:
- Task statuses (pending, running, validating, passed, failed)
- Current batch of concurrent tasks
- Completed branches ready for rebase
- Validation errors for retry

Check status anytime with:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/orchestrator.py status
```

## Next Steps

After design review:
1. `/swiss-cheese:status` - View current task status
2. `/swiss-cheese:loop` - Run orchestrated execution until complete
3. `/swiss-cheese:gate <layer>` - Run specific layer manually

Or let the orchestrator dispatch tasks automatically via hooks.

## Reset State

To start fresh:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/orchestrator.py reset
```

Remember: The goal is defense in depth with maximum parallelism. Each layer is independent and thorough.
