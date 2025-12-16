#!/usr/bin/env python3
"""
Multi-agent worktree orchestrator for Claude Code hooks.
Reads TOML requirements, schedules via topological sort, spawns subagents in worktrees.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field, asdict
from enum import Enum
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any
from datetime import datetime


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    VALIDATING = "validating"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Task:
    name: str
    layer: str
    description: str
    depends_on: list[str]
    branch: str
    prompt_template: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    iteration: int = 0
    worktree_path: str | None = None
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class Layer:
    name: str
    description: str
    depends_on: list[str]
    validators: list[str]


@dataclass
class OrchestratorState:
    """Persisted state across hook invocations."""
    tasks: dict[str, dict]
    layers: dict[str, dict]
    validators: dict[str, list[str]]
    max_iterations: int
    max_parallel: int
    completed_branches: list[str]
    current_batch: list[str]
    design_doc: str | None = None

    @classmethod
    def load(cls, path: Path) -> "OrchestratorState | None":
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                return cls(**data)
        return None

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)


# Paths - derived from environment or defaults
PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd()))
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).parent.parent))
STATE_FILE = PROJECT_DIR / ".claude" / "orchestrator_state.json"
WORKTREE_BASE = PROJECT_DIR / ".worktrees"


def find_design_document() -> Path | None:
    """Find design document - check common locations."""
    candidates = [
        PROJECT_DIR / "design.toml",
        PROJECT_DIR / "requirements.toml",
        PROJECT_DIR / "swiss-cheese.toml",
        PROJECT_DIR / ".claude" / "design.toml",
        PROJECT_DIR / "docs" / "design.toml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def parse_requirements(path: Path) -> tuple[dict, dict, dict, int, int]:
    """Parse TOML requirements into layers, tasks, validators."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    # Parse layers with defaults
    layers = {}
    for name, cfg in data.get("layers", {}).items():
        layers[name] = {
            "name": name,
            "description": cfg.get("description", ""),
            "depends_on": cfg.get("depends_on", []),
            "validators": cfg.get("validation", cfg.get("validators", [])),
            "order": cfg.get("order", 99),
            "optional": cfg.get("optional", False),
        }

    # Parse tasks with worktree branch generation
    worktree_config = data.get("worktree", {})
    branch_prefix = worktree_config.get("branch_prefix", "swiss-cheese")

    tasks = {}
    for name, cfg in data.get("tasks", {}).items():
        branch = cfg.get("branch", f"{branch_prefix}/{name}")
        tasks[name] = {
            "name": name,
            "layer": cfg["layer"],
            "description": cfg.get("description", ""),
            "depends_on": cfg.get("depends_on", []),
            "branch": branch,
            "prompt_template": cfg.get("prompt_template"),
            "agent": cfg.get("agent"),
            "command": cfg.get("command"),
            "optional": cfg.get("optional", False),
            "status": TaskStatus.PENDING.value,
            "iteration": 0,
            "worktree_path": None,
            "validation_errors": [],
        }

    # Parse validators (either as commands or gate configs)
    validators = {}
    for name, cfg in data.get("validators", {}).items():
        if isinstance(cfg, dict):
            validators[name] = cfg.get("command", cfg.get("cmd", []))
        else:
            validators[name] = cfg

    # Also pull validators from gates section
    for name, cfg in data.get("gates", {}).items():
        if "commands" in cfg:
            for cmd_cfg in cfg["commands"]:
                cmd_name = cmd_cfg.get("name", name)
                validators[cmd_name] = cmd_cfg.get("cmd", "")

    max_iter = data.get("project", {}).get("max_iterations", 5)
    max_parallel = data.get("project", {}).get("max_parallel_agents", 4)

    return layers, tasks, validators, max_iter, max_parallel


def init_state(design_doc: Path | None = None) -> OrchestratorState:
    """Initialize orchestrator state from design document."""
    if design_doc is None:
        design_doc = find_design_document()

    if design_doc is None or not design_doc.exists():
        # Return empty state - no orchestration configured
        return OrchestratorState(
            tasks={},
            layers={},
            validators={},
            max_iterations=5,
            max_parallel=4,
            completed_branches=[],
            current_batch=[],
            design_doc=None,
        )

    layers, tasks, validators, max_iter, max_parallel = parse_requirements(design_doc)
    return OrchestratorState(
        tasks=tasks,
        layers=layers,
        validators=validators,
        max_iterations=max_iter,
        max_parallel=max_parallel,
        completed_branches=[],
        current_batch=[],
        design_doc=str(design_doc),
    )


def get_ready_tasks(state: OrchestratorState) -> list[str]:
    """Get tasks ready to run via topological sort."""
    if not state.tasks:
        return []

    # Build dependency graph
    graph: dict[str, set[str]] = {}
    for name, task in state.tasks.items():
        deps = set(task["depends_on"])
        # Also add implicit layer dependencies
        layer = state.layers.get(task["layer"], {})
        for layer_dep in layer.get("depends_on", []):
            # Find tasks in dependent layers that must complete
            for other_name, other_task in state.tasks.items():
                if other_task["layer"] == layer_dep:
                    deps.add(other_name)
        graph[name] = deps

    sorter: TopologicalSorter[str] = TopologicalSorter(graph)
    sorter.prepare()

    ready: list[str] = []

    while sorter.is_active():
        batch = list(sorter.get_ready())
        for name in batch:
            task = state.tasks[name]
            if task["status"] == TaskStatus.PENDING.value:
                # Check if all deps are satisfied
                deps_satisfied = all(
                    state.tasks.get(dep, {}).get("status") == TaskStatus.PASSED.value
                    for dep in task["depends_on"]
                )
                if deps_satisfied:
                    ready.append(name)
            sorter.done(name)

    return ready[:state.max_parallel]


def create_worktree(branch: str, base_ref: str = "main") -> Path:
    """Create git worktree for a branch."""
    worktree_path = WORKTREE_BASE / branch.replace("/", "-")
    WORKTREE_BASE.mkdir(parents=True, exist_ok=True)

    if worktree_path.exists():
        return worktree_path

    # Create branch if needed
    result = subprocess.run(
        ["git", "branch", "--list", branch],
        capture_output=True, cwd=PROJECT_DIR
    )
    if not result.stdout.strip():
        subprocess.run(
            ["git", "branch", branch, base_ref],
            cwd=PROJECT_DIR, check=True
        )

    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), branch],
        cwd=PROJECT_DIR, check=True
    )
    return worktree_path


def run_validators(task: dict, state: OrchestratorState) -> tuple[bool, list[str]]:
    """Run validators for a task's layer."""
    layer = state.layers.get(task["layer"], {})
    validator_names = layer.get("validators", [])
    worktree = Path(task["worktree_path"]) if task["worktree_path"] else PROJECT_DIR

    errors: list[str] = []
    for validator_name in validator_names:
        cmd = state.validators.get(validator_name)
        if not cmd:
            continue

        try:
            result = subprocess.run(
                cmd, cwd=worktree, capture_output=True,
                shell=isinstance(cmd, str), timeout=300
            )
            if result.returncode != 0:
                stderr = result.stderr.decode() if result.stderr else ""
                errors.append(f"[{validator_name}] {stderr[:500]}")
        except subprocess.TimeoutExpired:
            errors.append(f"[{validator_name}] Timeout after 5 minutes")
        except Exception as e:
            errors.append(f"[{validator_name}] Error: {str(e)}")

    return len(errors) == 0, errors


def build_subagent_prompt(task: dict, state: OrchestratorState) -> str:
    """Build prompt for subagent."""
    layer = state.layers.get(task["layer"], {})

    prompt = f"""## Task: {task['name']}

**Layer**: {task['layer']} - {layer.get('description', '')}
**Description**: {task['description']}
**Working directory**: {task['worktree_path'] or PROJECT_DIR}
**Iteration**: {task['iteration'] + 1}/{state.max_iterations}

### Requirements
- Write safe, verifiable Rust code (prefer safe abstractions over unsafe)
- Include property-based tests where applicable
- Add Kani proof harnesses for critical invariants
- Document preconditions, postconditions, and invariants
- Follow embedded Rust best practices (no_std compatible where needed)

### Validators that must pass
{chr(10).join(f'- {v}' for v in layer.get('validators', []))}
"""

    if task["validation_errors"]:
        prompt += f"""
### Previous validation failures (fix these):
{chr(10).join(task['validation_errors'][-3:])}
"""

    if task.get("command"):
        prompt += f"""
### Command to verify
```bash
{task['command']}
```
"""

    return prompt


def dispatch_subagents(state: OrchestratorState) -> dict:
    """Dispatch ready tasks as subagents. Returns JSON for Claude."""
    if not state.tasks:
        return {"continue": True}  # No orchestration configured

    ready = get_ready_tasks(state)

    if not ready:
        # Check if all done
        all_done = all(
            t["status"] in (TaskStatus.PASSED.value, TaskStatus.FAILED.value)
            for t in state.tasks.values()
        )
        if all_done:
            failed = [n for n, t in state.tasks.items() if t["status"] == TaskStatus.FAILED.value]
            if failed:
                return {
                    "continue": True,
                    "systemMessage": f"[Swiss Cheese] Tasks complete. Failed: {', '.join(failed)}"
                }
            return {
                "continue": True,
                "systemMessage": "[Swiss Cheese] All tasks complete. Ready to rebase branches."
            }
        return {
            "continue": True,
            "systemMessage": "[Swiss Cheese] Waiting for dependencies..."
        }

    # Create worktrees and build prompts
    subagent_prompts: list[str] = []
    for task_name in ready:
        task = state.tasks[task_name]

        # Create worktree
        try:
            worktree = create_worktree(task["branch"])
            task["worktree_path"] = str(worktree)
        except subprocess.CalledProcessError as e:
            task["worktree_path"] = str(PROJECT_DIR)
            subagent_prompts.append(f"### Task: {task_name}\n(Worktree creation failed, using main directory)\n")

        task["status"] = TaskStatus.RUNNING.value

        prompt = build_subagent_prompt(task, state)
        agent = task.get("agent", "implementation-agent")
        subagent_prompts.append(f"### Subagent ({agent}): {task_name}\n{prompt}")

    state.current_batch = ready
    state.save(STATE_FILE)

    # Inject context for Claude to spawn subagents
    context = f"""## [Swiss Cheese] Orchestrator: Spawning {len(ready)} tasks

The following tasks are ready to run concurrently. Use the Task tool to spawn subagents for each, or work sequentially if needed:

{chr(10).join(subagent_prompts)}

After completing each task, commit changes with message format: `[swiss-cheese] <task_name> iteration <N>`
"""

    return {
        "continue": True,
        "systemMessage": context
    }


def on_subagent_complete(state: OrchestratorState, input_data: dict) -> dict:
    """Handle subagent completion - run validators, update state."""
    if not state.tasks:
        return {"decision": "approve"}

    # Validate all running tasks in current batch
    for task_name in list(state.current_batch):
        task = state.tasks.get(task_name)
        if not task or task["status"] != TaskStatus.RUNNING.value:
            continue

        task["status"] = TaskStatus.VALIDATING.value
        passed, errors = run_validators(task, state)

        if passed:
            task["status"] = TaskStatus.PASSED.value
            state.completed_branches.append(task["branch"])
            msg = f"[Swiss Cheese] {task_name} passed all validators"
        else:
            task["iteration"] += 1
            task["validation_errors"].extend(errors)

            if task["iteration"] >= state.max_iterations:
                task["status"] = TaskStatus.FAILED.value
                msg = f"[Swiss Cheese] {task_name} failed after {state.max_iterations} iterations"
            else:
                task["status"] = TaskStatus.PENDING.value  # Retry
                msg = f"[Swiss Cheese] {task_name} failed validation, retrying ({task['iteration']}/{state.max_iterations})"

        print(msg, file=sys.stderr)

    state.current_batch = []
    state.save(STATE_FILE)

    # Check if we should continue
    pending = [
        name for name, t in state.tasks.items()
        if t["status"] == TaskStatus.PENDING.value
    ]

    if pending:
        return {
            "decision": "block",
            "reason": f"[Swiss Cheese] Continue orchestration: {len(pending)} tasks pending"
        }

    return {"decision": "approve"}


def rebase_completed(state: OrchestratorState) -> bool:
    """Rebase completed branches in topological order."""
    if not state.completed_branches:
        return True

    # Sort branches by task dependency order
    task_order = []
    graph = {name: set(t["depends_on"]) for name, t in state.tasks.items()}
    sorter: TopologicalSorter[str] = TopologicalSorter(graph)

    for name in sorter.static_order():
        task = state.tasks.get(name)
        if task and task["branch"] in state.completed_branches:
            task_order.append(task["branch"])

    # Rebase chain
    onto = "main"
    for branch in task_order:
        result = subprocess.run(
            ["git", "rebase", onto, branch],
            cwd=PROJECT_DIR, capture_output=True
        )
        if result.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], cwd=PROJECT_DIR)
            return False
        onto = branch

    return True


def get_status(state: OrchestratorState) -> dict:
    """Get current orchestration status."""
    if not state.tasks:
        return {
            "message": "[Swiss Cheese] No orchestration configured. Create a design.toml file."
        }

    status_counts = {s.value: 0 for s in TaskStatus}
    for task in state.tasks.values():
        status_counts[task["status"]] += 1

    task_status = {
        name: {
            "status": t["status"],
            "layer": t["layer"],
            "iteration": t["iteration"],
            "branch": t["branch"],
        }
        for name, t in state.tasks.items()
    }

    return {
        "design_doc": state.design_doc,
        "status_counts": status_counts,
        "tasks": task_status,
        "current_batch": state.current_batch,
        "completed_branches": state.completed_branches,
    }


def reset_state() -> dict:
    """Reset orchestrator state."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    return {"message": "[Swiss Cheese] Orchestrator state reset."}


def main():
    if len(sys.argv) < 2:
        print("Usage: orchestrator.py <command> [design_doc]", file=sys.stderr)
        print("Commands: dispatch, on_subagent_complete, rebase, status, reset, init", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    design_doc = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    # Read stdin for hook input
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        input_data = {}

    # Handle reset command first
    if command == "reset":
        result = reset_state()
        print(json.dumps(result))
        sys.exit(0)

    # Handle init command
    if command == "init":
        state = init_state(design_doc)
        state.save(STATE_FILE)
        print(json.dumps({
            "message": f"[Swiss Cheese] Initialized with {len(state.tasks)} tasks from {state.design_doc or 'defaults'}"
        }))
        sys.exit(0)

    # Load or init state
    state = OrchestratorState.load(STATE_FILE)
    if state is None:
        state = init_state(design_doc)
        if state.tasks:
            state.save(STATE_FILE)

    if command == "dispatch":
        result = dispatch_subagents(state)
        print(json.dumps(result))
        sys.exit(0)

    elif command == "on_subagent_complete":
        result = on_subagent_complete(state, input_data)
        print(json.dumps(result))
        sys.exit(0)

    elif command == "rebase":
        success = rebase_completed(state)
        if success:
            print(json.dumps({"systemMessage": "[Swiss Cheese] Rebase complete"}))
        else:
            print(json.dumps({"systemMessage": "[Swiss Cheese] Rebase failed - resolve conflicts manually"}))
        sys.exit(0 if success else 1)

    elif command == "status":
        result = get_status(state)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
