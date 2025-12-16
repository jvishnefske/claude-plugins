---
description: Path to design document (TOML or markdown)
arguments:
  - name: design_doc
    description: Path to design document (TOML)
    required: false
---

You are starting a safety-critical development session using the Swiss Cheese Model.

## Swiss Cheese Model Overview

Like the NASA Swiss Cheese Model for accident prevention, this workflow uses 9 independent verification layers. Each layer catches defects that slip through previous layers.

```
Layer 1: Requirements    → Formalize requirements with testable criteria
Layer 2: Architecture    → Design type-safe, ownership-correct architecture
Layer 3: TDD             → Write comprehensive tests BEFORE implementation
Layer 4: Implementation  → Implement code to pass tests
Layer 5: Static Analysis → Run Clippy, cargo-audit, cargo-deny
Layer 6: Formal Verify   → Prove properties with Kani (optional)
Layer 7: Dynamic Analysis→ Run Miri, fuzzing, coverage analysis
Layer 8: Review          → Independent fresh-eyes review
Layer 9: Safety Case     → Assemble safety case and make release decision
```

## Orchestration Architecture

The orchestrator runs on **Stop events only** and:
1. Validates the TOML design document against the schema
2. Tracks task/gate status in `/tmp` (invisible to you)
3. Runs **Makefile targets** for gate validation
4. Generates **traceability matrix** from test results
5. Blocks and continues until all gates pass

## Your Task

{{#if design_doc}}
1. Read the design document at: `{{design_doc}}`
2. Validate it matches the expected TOML schema
3. If valid, begin working on tasks for the current layer
4. The orchestrator will guide you through each layer
{{else}}
1. Look for design documents: `design.toml`, `swiss-cheese.toml`, `requirements.toml`
2. If none found, help create one using the schema below
3. Also create a `Makefile` with gate validation targets (see `examples/Makefile.swiss-cheese`)
{{/if}}

## Design Document Schema (TOML)

```toml
[project]
name = "project-name"           # Required
version = "0.1.0"               # Required
max_iterations = 5              # Optional, default 5
max_parallel_agents = 4         # Optional, default 4

[[requirements]]
id = "REQ-001"                  # Required: unique ID matching REQ-NNN
title = "Short title"           # Required
description = "Full description" # Required
priority = "high"               # Optional: critical|high|medium|low
acceptance_criteria = [         # Required: testable criteria
    "Criterion 1",
    "Criterion 2",
]

[tasks.task_name]
layer = "implementation"        # Required: one of 9 layers
description = "What this does"  # Required
depends_on = ["other_task"]     # Optional: task dependencies
requirements = ["REQ-001"]      # Optional: requirement IDs
agent = "implementation-agent"  # Optional: agent type
command = "cargo test"          # Optional: validation command

[gates.layer_name]
target = "validate-layer"       # Required: Makefile target
```

## Makefile Requirements

Your project needs a `Makefile` with targets for each layer:

```makefile
validate-requirements:    # Layer 1
validate-architecture:    # Layer 2
validate-tdd:             # Layer 3
validate-implementation:  # Layer 4 - cargo build && cargo test
validate-static-analysis: # Layer 5 - cargo clippy, audit, deny
validate-formal-verification:  # Layer 6 (optional)
validate-dynamic-analysis:     # Layer 7 - miri, coverage
validate-review:          # Layer 8
validate-safety-case:     # Layer 9
```

See `examples/Makefile.swiss-cheese` for a complete template.

## How It Works

1. You work on tasks for the current layer
2. When you try to stop, the orchestrator checks gate status
3. It runs `make validate-<layer>` to verify the gate
4. If the gate fails, you're prompted to fix issues and continue
5. If the gate passes, you advance to the next layer
6. This continues until all 9 layers pass

## Commands

- `/swiss-cheese:status` - View current layer and task status
- `/swiss-cheese:loop` - Continue orchestrated execution
- `/swiss-cheese:gate <layer>` - Run specific gate manually
- `/swiss-cheese:skip-layer <reason>` - Skip optional layer with justification
- `/swiss-cheese:cancel` - Cancel orchestration

## Traceability

The orchestrator maintains a traceability matrix linking:
- Requirements (REQ-001, etc.)
- Tasks that address each requirement
- Tests that verify each requirement

Name your tests like `test_req_001_*` for automatic traceability.

Final report saved to `.claude/traceability_matrix.json` on completion.
