# Swiss Cheese Loop Design

## Overview

Implement `/swiss-cheese:loop` — an iterative verification loop that runs the 4-layer gate sequence, dispatches subagents to fix failures, and retries until all gates pass or a retry limit is hit.

## Problem

The swiss-cheese plugin has gate validation infrastructure (Makefile targets, report generation, read-only hook) but no automated loop to drive the fix-verify cycle. Users must manually run gates, interpret failures, and fix issues. The loop automates this.

## Constraints

- **Context window**: The loop runs in the main conversation. Fix-it work is delegated to subagents (fresh context each) so the loop stays lean. Subagent results are summarized tersely.
- **Warm start**: Assumes `docs/plans/tasks.toml` and a Makefile with gate targets already exist (created via `/swiss-cheese:design` and `/swiss-cheese:gate`).
- **Retry limit**: 3 attempts per gate. On escalating retries, the subagent receives gate output plus a terse summary of prior attempts. After 3 failures, the loop stops and asks the user.

## Architecture

```
/swiss-cheese:loop (skill)
    |
    v
scripts/loop.py run          <-- runs gates, returns JSON state
    |
    v (gate_failed?)
Skill dispatches subagent    <-- fresh context, gate output + history
    |
    v (subagent done)
scripts/loop.py record-attempt --gate <name> --summary "..."
    |
    v (loop back to run)
scripts/loop.py run          <-- re-runs all gates from 1
    |
    v (all pass?)
/swiss-cheese:generate-reports
    |
    v
Done
```

## Components

### 1. `scripts/loop.py` — Loop Orchestrator

Python script with two subcommands:

#### `run`

1. Run `make validate-requirements`, `make validate-tdd`, `make validate-implementation`, `make validate-verify` sequentially
2. Stop at first failure
3. Read existing `loop-state.json` for retry counts and history
4. Increment retry count for the failing gate
5. Write updated `loop-state.json`
6. Print JSON to stdout with current state

Exit codes:
- 0: all gates passed
- 1: a gate failed (retries remain)
- 2: a gate failed (retry limit reached, user needed)

#### `record-attempt --gate <name> --summary "..."`

1. Read `loop-state.json`
2. Append summary string to history for the named gate
3. Write updated `loop-state.json`

#### State file: `.swiss-cheese/loop-state.json`

```json
{
  "status": "gate_failed",
  "iteration": 2,
  "current_gate": 3,
  "gate_name": "implementation",
  "gate_output": "test xyz failed... (truncated)",
  "retries": {
    "requirements": 0,
    "tdd": 0,
    "implementation": 2,
    "verify": 0
  },
  "history": {
    "implementation": [
      "Attempt 1: added missing From impl for ErrorKind",
      "Attempt 2: fixed lifetime in parse_config return type"
    ]
  }
}
```

#### Gate output truncation

Gate stdout+stderr is captured and truncated to 2000 characters in the state file. This keeps the state file small and prevents bloating subagent prompts.

### 2. `commands/loop.md` — Loop Skill

Skill executed by `/swiss-cheese:loop`. Thin control layer:

1. **Precondition check**: Verify Makefile and `docs/plans/tasks.toml` exist. If not, tell user to run `/swiss-cheese:design` and `/swiss-cheese:gate` first.
2. **Run `python3 scripts/loop.py run`**
3. **Read JSON output and act:**
   - Exit 0 (`"passed"`): Run `/swiss-cheese:generate-reports`, print summary, done.
   - Exit 1 (`"gate_failed"`): Dispatch appropriate subagent with gate output + history. After subagent returns, run `python3 scripts/loop.py record-attempt`. Loop back to step 2.
   - Exit 2 (`"user_needed"`): Print failure details and history, ask user for help.

#### Gate-to-agent mapping

| Failed gate      | Dispatched agent                  |
|------------------|-----------------------------------|
| requirements     | swiss-cheese:requirements-agent   |
| tdd              | swiss-cheese:tdd-agent            |
| implementation   | swiss-cheese:implementation-agent |
| verify           | swiss-cheese:implementation-agent |

#### Subagent prompt template

The skill constructs the subagent prompt from:
- Gate name and gate output (from loop.py JSON)
- History summaries of prior attempts (if any)
- Instruction to fix the issue and keep changes minimal

### 3. `tests/test_loop.py` — Unit Tests

Test cases using same patterns as existing test suite (frozen dataclasses, tempdir, mocked subprocess):

- **Gate execution**: mock `make validate-*`, verify pass/fail detection
- **Sequential ordering**: gates run 1-4, stop at first failure
- **Retry tracking**: count increments per gate, different gate resets that gate's count
- **History recording**: `record-attempt` appends, capped at 3
- **State persistence**: JSON round-trip, handles missing file
- **All-pass path**: exit 0, status `"passed"`
- **User-needed path**: exit 2 after 3 retries
- **Gate output capture**: stdout+stderr captured, truncated to 2000 chars

## Design decisions

**Python script + skill, not pure skill**: Retry counting and gate execution should be deterministic, not dependent on Claude following instructions. The script is the source of truth for loop state.

**Script does not dispatch subagents**: The script only runs gates and tracks state. The skill reads the script's output and handles subagent dispatch. This keeps the Python testable (no Claude API dependency) and the skill simple (just reads JSON and acts).

**Full gate re-run each iteration**: A subagent fixing gate 3 could break gate 1. Running all gates from the start each iteration is safer than resuming from the last failure.

**3-attempt retry limit with escalating context**: First attempt gets gate output only. Second and third get gate output plus terse summaries of prior attempts. After 3 failures, the loop stops. This bounds cost while giving subagents progressively more context.

## Files to create/modify

| File | Action |
|------|--------|
| `swiss-cheese/scripts/loop.py` | Create |
| `swiss-cheese/commands/loop.md` | Create |
| `swiss-cheese/tests/test_loop.py` | Create |
| `design.md` | Update FR-006 checkboxes |
