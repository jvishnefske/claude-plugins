---
description: Analyze requirements and produce TOML task specification
arguments:
  - name: requirements_source
    description: Path to requirements document, URL, or description
    required: false
---

You are conducting requirements analysis to produce a task specification.

## Goal

Produce `docs/plans/tasks.toml` - a validated task list ready for implementation.

## Process

{{#if requirements_source}}
1. Read and analyze: `{{requirements_source}}`
{{else}}
1. Look for existing requirements in: README.md, docs/, requirements.md, design.md
{{/if}}
2. Extract functional requirements with testable acceptance criteria
3. Break into implementable tasks with dependencies
4. Validate the task graph (no cycles, all deps exist)
5. Write `docs/plans/tasks.toml`

## Task Specification Schema (TOML)

```toml
version = 1
status = "ready_for_implementation"  # or: "draft", "needs_review"

[project]
name = "project-name"
description = "Brief project description"
[[tasks]]
id = "task-001"
title = "Short imperative title"
acceptance = "Specific testable criteria"
deps = []  # List of task IDs this depends on
status = "pending"  # pending | in_progress | complete
spec_file = "specs/task-001.md"  # Optional: detailed specification

[[tasks]]
id = "task-002"
title = "Another task"
acceptance = "Tests pass, no compiler warnings"
deps = ["task-001"]  # Depends on task-001
status = "pending"
```

## Requirements for Each Task

1. **id**: Unique identifier (task-NNN format)
2. **title**: Short, imperative description (e.g., "Implement user login")
3. **acceptance**: Testable criteria - what "done" looks like
4. **deps**: Array of task IDs that must complete first
5. **status**: Always start as `pending`
6. **spec_file**: Optional path to detailed specification

## Validation Checklist

Before setting `status = "ready_for_implementation"`:

- [ ] All tasks have unique IDs
- [ ] All dependency references are valid task IDs
- [ ] No circular dependencies (topological sort must succeed)
- [ ] Each task has testable acceptance criteria
- [ ] Dependencies form a valid DAG (directed acyclic graph)

## Output

Create `docs/plans/tasks.toml` with:
1. All requirements broken into tasks
2. Dependencies correctly mapped
3. Testable acceptance criteria
4. Status set to `ready_for_implementation`

## Makefile Integration

Ensure a `Makefile` exists with verification target:

```makefile
.PHONY: verify

verify:
	cargo build --all-targets 2>&1 | grep -E "^warning:" && exit 1 || true
	cargo test --all-features
	cargo clippy --all-targets -- -D warnings
	cargo fmt --check
```

The `Stop` hook runs `make verify` before allowing completion.

## Next Steps

After completing the design:
1. Run `/swiss-cheese:implementation` to begin TDD workflow
2. The SessionStart hook parses tasks.toml and shows ready tasks
3. Work through tasks in topological order
