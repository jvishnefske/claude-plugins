---
description: Start iterative refinement loop until all gates pass
---

You are starting the Swiss Cheese orchestrated execution loop. This uses **concurrent task execution** with topological sorting to maximize parallelism while respecting dependencies.

## Orchestrated Loop Algorithm

```
while not all_tasks_passed:
    # Get all tasks with satisfied dependencies (can run in parallel)
    ready_tasks = topological_sort(pending_tasks)

    # Dispatch up to max_parallel_agents concurrently
    for task in ready_tasks[:max_parallel]:
        worktree = create_worktree(task.branch)
        spawn_subagent(task, worktree)

    # Wait for batch completion
    await all_subagents_complete()

    # Validate each task
    for task in current_batch:
        if validators_pass(task):
            task.status = PASSED
            completed_branches.append(task.branch)
        else:
            task.iteration += 1
            if task.iteration < max_iterations:
                task.status = PENDING  # Retry
            else:
                task.status = FAILED
```

## Execution Rules

1. **Parallel Execution**: Tasks without interdependencies run concurrently in separate worktrees
2. **Topological Order**: Dependencies are respected via graph sorting
3. **Auto-Retry**: Failed tasks retry automatically (up to max_iterations)
4. **Validation Gates**: Validators run after each task completion
5. **Branch Isolation**: Each task works in its own git branch
6. **Linear Rebase**: Completed branches are rebased in dependency order

## Task Dependencies (Example)

```
parse_requirements ──→ formalize_constraints ──→ design_modules ──→ define_interfaces
                                                                           │
                                    ┌──────────────────────────────────────┼──────────────────┐
                                    ↓                                      ↓                  ↓
                            write_unit_tests                    write_property_tests   write_integration_tests
                                    │                                      │                  │
                                    └──────────────────┬───────────────────┘                  │
                                                       ↓                                      │
                                               implement_core ←───────────────────────────────┘
                                                       │
                    ┌──────────────────────────────────┼──────────────────────────────────────┐
                    ↓                                  ↓                                      ↓
               run_clippy                          run_miri                            run_kani
               run_audit                       measure_coverage
               run_deny                         run_fuzzing
                    │                                  │                                      │
                    └──────────────────────────────────┼──────────────────────────────────────┘
                                                       ↓
                                              independent_review
                                                       ↓
                                             assemble_safety_case
```

## Starting the Loop

1. Check orchestrator status:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/orchestrator.py status
   ```

2. The orchestrator dispatches ready tasks automatically via hooks

3. For manual dispatch, signal readiness and the `UserPromptSubmit` hook will dispatch

4. Monitor progress with `/swiss-cheese:status`

5. Cancel with `/swiss-cheese:cancel`

## Progress Tracking

The orchestrator tracks:
- Task status (pending, running, validating, passed, failed)
- Current batch of concurrent tasks
- Validation errors for retries
- Completed branches ready for rebase

## Completion

When all tasks pass:
1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/orchestrator.py rebase` to merge branches
2. Or manually rebase: branches are in `.worktrees/` directory

Begin the orchestrated loop now. The hooks will automatically dispatch tasks as you work.
