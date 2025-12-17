---
description: Use this skill when the user asks about "Swiss Cheese Model", "verified Rust", "verification layers", "how to use swiss-cheese plugin", "rust verification workflow", "9-layer verification", "Makefile gates", or needs guidance on using the Swiss Cheese verification plugin.
---

# Swiss Cheese Model - Verified Development Guide

The Swiss Cheese Model plugin implements a 9-layer verification approach for verified development, inspired by NASA's Swiss Cheese Model for accident prevention.

## Core Concept

Like layers of Swiss cheese, each verification layer catches defects that slip through previous layers. No single layer is perfect, but together they provide defense in depth.

## Architecture

The orchestrator runs on **Stop events only** and:
1. Validates the TOML design document against a schema
2. Tracks task/gate status in `/tmp` (invisible to agent)
3. Runs **Makefile targets** for gate validation
4. Generates **traceability matrix** from test results
5. Blocks and continues until all gates pass

## The 9 Verification Layers

| Layer | Name | Makefile Target | Purpose |
|-------|------|-----------------|---------|
| 1 | Requirements | `validate-requirements` | Formalize testable requirements |
| 2 | Architecture | `validate-architecture` | Design type-safe architecture |
| 3 | TDD | `validate-tdd` | Write tests BEFORE implementation |
| 4 | Implementation | `validate-implementation` | Code to pass tests |
| 5 | Static Analysis | `validate-static-analysis` | Clippy, audit, deny |
| 6 | Formal Verification | `validate-formal-verification` | Kani proofs (optional) |
| 7 | Dynamic Analysis | `validate-dynamic-analysis` | Miri, coverage |
| 8 | Review | `validate-review` | Independent code review |
| 9 | Safety Case | `validate-safety-case` | Assemble evidence |

## Quick Start

1. Create `design.toml` with requirements and tasks
2. Create `Makefile` with gate validation targets
3. Run `/swiss-cheese` to start
4. Work on tasks - orchestrator guides you through layers
5. Gates validate automatically on Stop events

## Design Document Format (TOML)

```toml
[project]
name = "my-project"
version = "0.1.0"
max_iterations = 5

[[requirements]]
id = "REQ-001"
title = "Safe Input Parsing"
description = "System must safely parse untrusted input"
priority = "critical"
acceptance_criteria = [
    "No panics on malformed input",
    "All errors are recoverable",
]

[tasks.implement_parser]
layer = "implementation"
description = "Implement safe parser"
depends_on = ["write_parser_tests"]
requirements = ["REQ-001"]

[gates.implementation]
target = "validate-implementation"
```

## Makefile Requirements

```makefile
validate-requirements:
	@test -f design.toml
	@python3 -c "import tomllib; tomllib.load(open('design.toml', 'rb'))"

validate-implementation:
	cargo build --all-targets
	cargo test --all-features

validate-static-analysis:
	cargo clippy --all-targets -- -D warnings
	cargo audit || true
```

## Commands

| Command | Purpose |
|---------|---------|
| `/swiss-cheese` | Start verification session |
| `/swiss-cheese:status` | Show current status |
| `/swiss-cheese:gate <name>` | Run specific gate |
| `/swiss-cheese:loop` | Continue orchestration |
| `/swiss-cheese:skip-layer <reason>` | Skip optional layer |
| `/swiss-cheese:cancel` | Cancel orchestration |

## Traceability

Name tests to match requirements for automatic linking:
- `REQ-001` → `test_req_001_*`

The orchestrator generates `.claude/traceability_matrix.json`:

```json
{
  "requirements": [
    {"id": "REQ-001", "tests": ["test_req_001_valid"], "covered": true}
  ],
  "coverage": {"REQ-001": "verified"}
}
```

## How Orchestration Works

```
User works on tasks
        ↓
User tries to stop
        ↓
orchestrate.py runs (Stop hook)
        ↓
Validates design.toml against schema
        ↓
Checks current layer status
        ↓
Runs: make validate-<layer>
        ↓
    ┌───────────────────┐
    │ Gate passed?      │
    └───────────────────┘
      │ Yes         │ No
      ↓             ↓
   Advance       Block and
   to next       prompt to
   layer         fix issues
      │             │
      └─────────────┘
              ↓
        Continue loop
              ↓
    All layers passed?
      │ Yes         │ No
      ↓             ↓
   Complete      Continue
   (approve)     working
```

## Best Practices

1. **Don't skip layers** unless absolutely necessary
2. **Document skip decisions** with clear justification
3. **Name tests** to match requirement IDs for traceability
4. **Use the schema** - design.toml is validated automatically
5. **Check gate output** when failures occur
6. **Create comprehensive Makefile** with all gate targets

## Files

| File | Purpose |
|------|---------|
| `design.toml` | Requirements, tasks, gates |
| `Makefile` | Gate validation targets |
| `/tmp/swiss_cheese_*.json` | Orchestrator status (internal) |
| `.claude/traceability_matrix.json` | Final traceability report |
