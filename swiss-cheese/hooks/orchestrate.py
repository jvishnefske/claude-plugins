#!/usr/bin/env python3
"""
Swiss Cheese Orchestrator - Parallel Subagent Dispatch with Worktrees

This orchestrator runs on Stop events and:
1. Validates TOML design documents against schema
2. Creates git worktrees for parallel task execution
3. Dispatches multiple subagents via Task tool prompts
4. Tracks task/gate status in /tmp (invisible to agent)
5. Runs Makefile targets for gate validation
6. Generates traceability matrix

The key innovation: outputs prompts that instruct Claude to spawn
multiple Task tools in parallel, each working in its own worktree.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from schema import validate_design_document, get_schema_for_agent, LAYERS


class TaskStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"  # Subagent spawned, working
    COMPLETED = "completed"    # Work done, needs validation
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class GateStatus(str, Enum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class OrchestratorStatus:
    """Status stored in /tmp - invisible to agent."""
    project_name: str
    design_doc_path: str
    design_doc_hash: str
    created_at: str
    updated_at: str
    current_layer: str
    tasks: dict[str, dict] = field(default_factory=dict)
    gates: dict[str, dict] = field(default_factory=dict)
    traceability: dict[str, dict] = field(default_factory=dict)
    iteration: int = 0
    max_iterations: int = 5
    max_parallel: int = 4

    @classmethod
    def load(cls, path: Path) -> "OrchestratorStatus | None":
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                return cls(**data)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def save(self, path: Path):
        self.updated_at = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)


# Environment
PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd()))
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).parent.parent))
WORKTREE_BASE = PROJECT_DIR / ".worktrees"


def get_status_file_path(project_name: str) -> Path:
    """Get status file path in /tmp based on project directory."""
    project_hash = hashlib.md5(str(PROJECT_DIR).encode()).hexdigest()[:8]
    return Path(f"/tmp/swiss_cheese_{project_hash}.json")


def find_design_document() -> Path | None:
    """Find TOML design document in common locations."""
    candidates = [
        PROJECT_DIR / "design.toml",
        PROJECT_DIR / "swiss-cheese.toml",
        PROJECT_DIR / "requirements.toml",
        PROJECT_DIR / ".claude" / "design.toml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def compute_file_hash(path: Path) -> str:
    """Compute MD5 hash of file contents."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def parse_design_document(path: Path) -> tuple[dict, Any]:
    """Parse and validate TOML design document."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    validation = validate_design_document(data)
    return data, validation


def create_worktree(task_name: str, branch: str) -> Path | None:
    """Create git worktree for a task. Returns worktree path or None on failure."""
    worktree_path = WORKTREE_BASE / task_name.replace("/", "-")

    if worktree_path.exists():
        return worktree_path

    WORKTREE_BASE.mkdir(parents=True, exist_ok=True)

    try:
        # Check if branch exists
        result = subprocess.run(
            ["git", "branch", "--list", branch],
            capture_output=True, cwd=PROJECT_DIR
        )

        if not result.stdout.strip():
            # Create branch from current HEAD
            subprocess.run(
                ["git", "branch", branch],
                cwd=PROJECT_DIR, check=True, capture_output=True
            )

        # Create worktree
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch],
            cwd=PROJECT_DIR, check=True, capture_output=True
        )
        return worktree_path
    except subprocess.CalledProcessError:
        return None


def get_main_branch() -> str:
    """Get the name of the main branch (main or master)."""
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=PROJECT_DIR, capture_output=True
        )
        if result.returncode == 0:
            # refs/remotes/origin/main -> main
            return result.stdout.decode().strip().split("/")[-1]
    except Exception:
        pass

    # Fallback: check if main or master exists
    for branch in ["main", "master"]:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=PROJECT_DIR, capture_output=True
        )
        if result.returncode == 0:
            return branch

    return "main"


def rebase_worktree_to_main(task: dict) -> tuple[bool, str]:
    """Rebase a task's worktree branch onto main and merge.

    Returns (success, message).
    """
    worktree_path = task.get("worktree_path")
    branch = task.get("branch")

    if not worktree_path or not branch:
        return True, "No worktree to rebase"

    worktree = Path(worktree_path)
    if not worktree.exists():
        return True, "Worktree doesn't exist"

    main_branch = get_main_branch()

    try:
        # 1. Fetch latest main in the worktree
        subprocess.run(
            ["git", "fetch", "origin", main_branch],
            cwd=worktree, capture_output=True, check=True
        )

        # 2. Rebase the task branch onto main
        result = subprocess.run(
            ["git", "rebase", f"origin/{main_branch}"],
            cwd=worktree, capture_output=True
        )

        if result.returncode != 0:
            # Rebase conflict - abort and report
            subprocess.run(["git", "rebase", "--abort"], cwd=worktree, capture_output=True)
            return False, f"Rebase conflict in {branch}: {result.stderr.decode()[:200]}"

        # 3. Switch to main in the main project dir and merge
        subprocess.run(
            ["git", "checkout", main_branch],
            cwd=PROJECT_DIR, capture_output=True, check=True
        )

        # 4. Merge the rebased branch (fast-forward if possible)
        result = subprocess.run(
            ["git", "merge", "--ff-only", branch],
            cwd=PROJECT_DIR, capture_output=True
        )

        if result.returncode != 0:
            # Try regular merge if ff fails
            result = subprocess.run(
                ["git", "merge", branch, "-m", f"[swiss-cheese] Merge {branch}"],
                cwd=PROJECT_DIR, capture_output=True
            )
            if result.returncode != 0:
                return False, f"Merge failed for {branch}: {result.stderr.decode()[:200]}"

        # 5. Clean up worktree
        subprocess.run(
            ["git", "worktree", "remove", str(worktree)],
            cwd=PROJECT_DIR, capture_output=True
        )

        return True, f"Merged {branch} into {main_branch}"

    except subprocess.CalledProcessError as e:
        return False, f"Git error: {e}"
    except Exception as e:
        return False, str(e)


def rebase_layer_tasks(status: OrchestratorStatus, layer: str) -> list[str]:
    """Rebase all passed tasks for a layer back to main.

    Returns list of error messages (empty if all succeeded).
    """
    errors = []

    for task_name, task in status.tasks.items():
        if task["layer"] == layer and task["status"] == TaskStatus.PASSED.value:
            success, message = rebase_worktree_to_main(task)
            if not success:
                errors.append(f"{task_name}: {message}")
            else:
                # Clear worktree path since it's been cleaned up
                task["worktree_path"] = None

    return errors


def check_worktree_has_new_commits(worktree_path: Path, since_hash: str | None) -> bool:
    """Check if worktree has new commits since a given hash."""
    if not worktree_path.exists():
        return False

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree_path, capture_output=True, check=True
        )
        current_hash = result.stdout.decode().strip()

        if since_hash is None:
            return True  # First check, assume work done

        return current_hash != since_hash
    except subprocess.CalledProcessError:
        return False


def get_worktree_head(worktree_path: Path) -> str | None:
    """Get HEAD commit hash of a worktree."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree_path, capture_output=True, check=True
        )
        return result.stdout.decode().strip()
    except subprocess.CalledProcessError:
        return None


def init_status_from_design(design_path: Path, data: dict) -> OrchestratorStatus:
    """Initialize status from validated design document."""
    project = data.get("project", {})
    now = datetime.now().isoformat()

    status = OrchestratorStatus(
        project_name=project.get("name", "unknown"),
        design_doc_path=str(design_path),
        design_doc_hash=compute_file_hash(design_path),
        created_at=now,
        updated_at=now,
        current_layer="requirements",
        max_iterations=project.get("max_iterations", 5),
        max_parallel=project.get("max_parallel_agents", 4),
    )

    # Initialize tasks from design
    for task_name, task in data.get("tasks", {}).items():
        branch = task.get("branch", f"swiss-cheese/{task_name}")
        status.tasks[task_name] = {
            "name": task_name,
            "layer": task["layer"],
            "description": task.get("description", ""),
            "depends_on": task.get("depends_on", []),
            "requirements": task.get("requirements", []),
            "agent": task.get("agent", "general-purpose"),
            "branch": branch,
            "status": TaskStatus.PENDING.value,
            "iteration": 0,
            "worktree_path": None,
            "last_commit": None,
            "last_error": None,
        }

    # Initialize gates from layers
    for layer_name, layer_info in LAYERS.items():
        status.gates[layer_name] = {
            "name": layer_name,
            "target": layer_info["makefile_target"],
            "status": GateStatus.NOT_RUN.value,
            "output": None,
            "exit_code": None,
        }

    # Initialize traceability from requirements
    for req in data.get("requirements", []):
        req_id = req.get("id")
        if req_id:
            task_ids = [
                name for name, task in data.get("tasks", {}).items()
                if req_id in task.get("requirements", [])
            ]
            status.traceability[req_id] = {
                "requirement_id": req_id,
                "title": req.get("title", ""),
                "task_ids": task_ids,
                "test_names": [],
                "status": "pending",
            }

    return status


def get_ready_tasks(status: OrchestratorStatus) -> list[str]:
    """Get tasks ready to dispatch (dependencies satisfied, in current layer)."""
    ready = []

    for task_name, task in status.tasks.items():
        # Only pending tasks in current layer
        if task["layer"] != status.current_layer:
            continue
        if task["status"] != TaskStatus.PENDING.value:
            continue

        # Check dependencies are satisfied
        deps_ok = all(
            status.tasks.get(dep, {}).get("status") == TaskStatus.PASSED.value
            for dep in task.get("depends_on", [])
        )

        if deps_ok:
            ready.append(task_name)

    return ready[:status.max_parallel]


def get_dispatched_tasks(status: OrchestratorStatus) -> list[str]:
    """Get tasks that have been dispatched (subagents working)."""
    return [
        name for name, task in status.tasks.items()
        if task["status"] == TaskStatus.DISPATCHED.value
    ]


def run_makefile_gate(target: str) -> tuple[bool, str, int]:
    """Run a Makefile target for gate validation."""
    makefile_path = PROJECT_DIR / "Makefile"
    if not makefile_path.exists():
        return False, "No Makefile found in project root", 1

    try:
        result = subprocess.run(
            ["make", target],
            cwd=PROJECT_DIR,
            capture_output=True,
            timeout=600,
        )
        output = result.stdout.decode() + result.stderr.decode()
        return result.returncode == 0, output[-2000:], result.returncode
    except subprocess.TimeoutExpired:
        return False, "Gate validation timed out after 10 minutes", -1
    except FileNotFoundError:
        return False, "make command not found", -1
    except Exception as e:
        return False, str(e), -1


def all_layer_tasks_complete(status: OrchestratorStatus, layer: str) -> bool:
    """Check if all tasks in a layer are passed/skipped."""
    layer_tasks = [t for t in status.tasks.values() if t["layer"] == layer]
    if not layer_tasks:
        return True
    return all(
        t["status"] in (TaskStatus.PASSED.value, TaskStatus.SKIPPED.value)
        for t in layer_tasks
    )


def get_next_layer(current: str) -> str | None:
    """Get the next layer in sequence."""
    layer_order = list(LAYERS.keys())
    try:
        idx = layer_order.index(current)
        if idx + 1 < len(layer_order):
            return layer_order[idx + 1]
    except ValueError:
        pass
    return None


def build_task_invocation(task_name: str, task: dict) -> str:
    """Build a single Task tool invocation string."""
    worktree = task.get("worktree_path", f".worktrees/{task_name}")
    agent = task.get("agent", "general-purpose")
    description = task.get("description", "No description")
    requirements = ", ".join(task.get("requirements", [])) or "None"
    layer = task.get("layer", "unknown")

    # Build the prompt for the subagent
    subagent_prompt = f"""You are working in worktree directory: {worktree}

## Task: {task_name}
**Layer**: {layer}
**Description**: {description}
**Requirements addressed**: {requirements}

## Instructions

1. Change to the worktree directory: `cd {worktree}`
2. Implement the task as described above
3. Write tests if this is a TDD or implementation task
4. Commit your changes with message: `[swiss-cheese] {task_name}`
5. Ensure code compiles and tests pass

When you complete this task, the orchestrator will validate the layer gate."""

    # Return formatted invocation (using angle brackets that won't be parsed as XML)
    return f"""
**{task_name}** ({agent}):
- Worktree: `{worktree}`
- Description: {description}

Use Task tool with:
- description: "{task_name}"
- subagent_type: "{agent}"
- prompt: (see below)

Prompt for {task_name}:
```
{subagent_prompt}
```
"""


def generate_dispatch_prompt(status: OrchestratorStatus, tasks: list[str]) -> str:
    """Generate prompt instructing Claude to spawn parallel Task tools."""

    layer_info = LAYERS.get(status.current_layer, {})

    prompt = f"""## [Swiss Cheese] Dispatch Parallel Subagents

**Current Layer**: {status.current_layer} - {layer_info.get("description", "")}
**Tasks to dispatch**: {len(tasks)}

You must now spawn {len(tasks)} subagent(s) using the Task tool.
**IMPORTANT**: Call ALL Task tools in a SINGLE message to run them in parallel.

"""

    for task_name in tasks:
        task = status.tasks[task_name]
        prompt += build_task_invocation(task_name, task)
        prompt += "\n---\n"

    prompt += f"""
## Parallel Execution

To run these tasks in parallel, include ALL {len(tasks)} Task tool calls in your next response.

Example structure (you must fill in the actual parameters):

```
I'll spawn {len(tasks)} parallel subagents to work on these tasks.

[Task tool call for {tasks[0]}]
{"[Task tool call for " + tasks[1] + "]" if len(tasks) > 1 else ""}
{"[Task tool call for " + tasks[2] + "]" if len(tasks) > 2 else ""}
...
```

After the subagents complete, try to stop again and the orchestrator will validate the gate.
"""

    return prompt


def check_dispatched_tasks_complete(status: OrchestratorStatus) -> list[str]:
    """Check which dispatched tasks have new commits (work done)."""
    completed = []

    for task_name in get_dispatched_tasks(status):
        task = status.tasks[task_name]
        worktree_path = task.get("worktree_path")

        if worktree_path and Path(worktree_path).exists():
            last_commit = task.get("last_commit")
            if check_worktree_has_new_commits(Path(worktree_path), last_commit):
                completed.append(task_name)

    return completed


def generate_traceability_report(status: OrchestratorStatus) -> dict:
    """Generate traceability matrix report."""
    report = {
        "project": status.project_name,
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_requirements": len(status.traceability),
            "verified": 0,
            "covered": 0,
            "pending": 0,
        },
        "matrix": [],
    }

    for req_id, trace in status.traceability.items():
        entry = {
            "requirement_id": req_id,
            "title": trace.get("title", ""),
            "tasks": trace["task_ids"],
            "tests": trace["test_names"],
            "status": trace["status"],
        }
        report["matrix"].append(entry)

        if trace["status"] == "verified":
            report["summary"]["verified"] += 1
        elif trace["status"] == "covered":
            report["summary"]["covered"] += 1
        else:
            report["summary"]["pending"] += 1

    return report


def check_transcript_for_task_completion(transcript_path: str, task_names: list[str]) -> list[str]:
    """Check transcript for evidence that tasks were worked on."""
    completed = []

    if not transcript_path:
        return completed

    # Expand ~ in path
    path = Path(transcript_path).expanduser()
    if not path.exists():
        return completed

    try:
        content = path.read_text()
        # Look for task-related commits or completion indicators
        for task_name in task_names:
            # Check for commit messages or task references
            if f"[swiss-cheese] {task_name}" in content or f"completed {task_name}" in content.lower():
                completed.append(task_name)
    except Exception:
        pass

    return completed


def identify_task_from_subagent(input_data: dict, status: OrchestratorStatus) -> str | None:
    """Identify which task a subagent was working on from its input data.

    SubagentStop input includes:
    - task_description: Short description we provided (matches task name)
    - subagent_type: The agent type used
    - result: The subagent's final output
    """
    # The task_description should match the task name we dispatched
    task_description = input_data.get("task_description", "")

    # Direct match on task name
    if task_description in status.tasks:
        return task_description

    # Try to find task by matching description
    for task_name, task in status.tasks.items():
        if task["status"] == TaskStatus.DISPATCHED.value:
            # Check if description matches
            if task_name in task_description or task_description in task.get("description", ""):
                return task_name

    # Fallback: check the subagent result for task references
    result = input_data.get("result", "")
    for task_name, task in status.tasks.items():
        if task["status"] == TaskStatus.DISPATCHED.value:
            if f"[swiss-cheese] {task_name}" in result:
                return task_name

    return None


def handle_subagent_stop(input_data: dict) -> dict:
    """Handle SubagentStop event - a subagent just finished.

    Input data from Claude Code:
    - task_description: The description we provided to the Task tool
    - subagent_type: The agent type that was used
    - result: The subagent's output/result
    - hook_event_name: "SubagentStop"
    """
    # Find design document
    design_path = find_design_document()
    if design_path is None:
        return {"continue": True}  # No swiss-cheese project active

    # Parse design document
    try:
        data, validation = parse_design_document(design_path)
    except Exception:
        return {"continue": True}  # Can't validate, let it continue

    if not validation.valid:
        return {"continue": True}  # Invalid doc, handle in Stop event

    # Load status
    status_path = get_status_file_path(data["project"]["name"])
    status = OrchestratorStatus.load(status_path)

    if status is None:
        return {"continue": True}  # No active orchestration

    # Identify which task completed
    task_name = identify_task_from_subagent(input_data, status)

    if task_name is None:
        # Can't identify task - might be a non-swiss-cheese subagent
        return {"continue": True}

    task = status.tasks.get(task_name)
    if task is None or task["status"] != TaskStatus.DISPATCHED.value:
        return {"continue": True}

    # Mark task as completed
    task["status"] = TaskStatus.COMPLETED.value

    # Update last_commit if we have a worktree
    if task.get("worktree_path"):
        worktree_path = Path(task["worktree_path"])
        if worktree_path.exists():
            task["last_commit"] = get_worktree_head(worktree_path)

    # Check if all dispatched tasks for this layer are now complete
    layer = task["layer"]
    layer_dispatched = [
        t for t in status.tasks.values()
        if t["layer"] == layer and t["status"] == TaskStatus.DISPATCHED.value
    ]

    if layer_dispatched:
        # Still have running subagents, save and continue
        status.save(status_path)
        return {
            "continue": True,
            "systemMessage": f"[Swiss Cheese] Task '{task_name}' completed. Waiting for {len(layer_dispatched)} more subagent(s)...",
        }

    # All subagents for this layer complete - run gate validation
    gate = status.gates.get(layer, {})
    target = gate.get("target", f"validate-{layer}")

    passed, output, exit_code = run_makefile_gate(target)
    gate["output"] = output
    gate["exit_code"] = exit_code

    if passed:
        gate["status"] = GateStatus.PASSED.value
        # Mark all completed tasks in this layer as passed
        for t_name, t in status.tasks.items():
            if t["layer"] == layer and t["status"] == TaskStatus.COMPLETED.value:
                t["status"] = TaskStatus.PASSED.value
                # Update traceability
                for req_id in t.get("requirements", []):
                    if req_id in status.traceability:
                        status.traceability[req_id]["status"] = "verified"

        # Rebase passed tasks back to main branch
        rebase_errors = rebase_layer_tasks(status, layer)
        if rebase_errors:
            # Rebase failed - report but don't block (tasks already passed gate)
            error_msg = "\n".join(rebase_errors)
            status.save(status_path)
            return {
                "continue": True,
                "systemMessage": f"""[Swiss Cheese] Gate '{layer}' passed but rebase failed:

{error_msg}

Please manually resolve conflicts and merge the branches.""",
            }

        # Check if layer is now complete
        if all_layer_tasks_complete(status, layer):
            next_layer = get_next_layer(layer)
            if next_layer:
                status.current_layer = next_layer
                status.save(status_path)
                return {
                    "continue": True,
                    "systemMessage": f"[Swiss Cheese] Layer '{layer}' complete! Advancing to '{next_layer}'.",
                }
            else:
                # All done!
                report = generate_traceability_report(status)
                report_path = PROJECT_DIR / ".claude" / "traceability_matrix.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                with open(report_path, "w") as f:
                    json.dump(report, f, indent=2)

                status.save(status_path)
                return {
                    "continue": True,
                    "systemMessage": f"[Swiss Cheese] All verification layers complete! Traceability matrix saved to {report_path}",
                }

        status.save(status_path)
        return {
            "continue": True,
            "systemMessage": f"[Swiss Cheese] Gate '{layer}' passed! Task '{task_name}' verified.",
        }
    else:
        gate["status"] = GateStatus.FAILED.value
        # Mark completed tasks as pending for retry
        for t_name, t in status.tasks.items():
            if t["layer"] == layer and t["status"] == TaskStatus.COMPLETED.value:
                t["iteration"] += 1
                if t["iteration"] >= status.max_iterations:
                    t["status"] = TaskStatus.FAILED.value
                    t["last_error"] = output[:500]
                else:
                    t["status"] = TaskStatus.PENDING.value
                    t["last_error"] = output[:500]

        status.save(status_path)
        return {
            "continue": True,
            "systemMessage": f"""[Swiss Cheese] Gate '{layer}' FAILED!

**Makefile target**: `make {target}`
**Exit code**: {exit_code}

Tasks reset to pending for retry. When you stop, the orchestrator will re-dispatch.

**Output**:
```
{output[:800]}
```""",
        }


def handle_stop_event(input_data: dict) -> dict:
    """Main Stop event handler - orchestration logic.

    Input data from Claude Code:
    - session_id: Current session identifier
    - transcript_path: Path to conversation transcript
    - hook_event_name: Should be "Stop"
    - stop_hook_active: Whether stop hook is active
    """
    # Extract useful fields from input
    transcript_path = input_data.get("transcript_path", "")

    # 1. Find design document
    design_path = find_design_document()
    if design_path is None:
        return {"decision": "approve"}

    # 2. Parse and validate design document
    try:
        data, validation = parse_design_document(design_path)
    except Exception as e:
        return {
            "decision": "block",
            "reason": f"[Swiss Cheese] Invalid design document: {e}\n\nPlease fix the TOML syntax.",
        }

    if not validation.valid:
        error_msg = "\n".join(f"- {e.path}: {e.message}" for e in validation.errors)
        schema = get_schema_for_agent()
        return {
            "decision": "block",
            "reason": f"""[Swiss Cheese] Design document validation failed:

{error_msg}

## Expected Schema

{schema}

Please update the design document to match the schema.
""",
        }

    # 3. Load or create status
    status_path = get_status_file_path(data["project"]["name"])
    status = OrchestratorStatus.load(status_path)

    current_hash = compute_file_hash(design_path)
    if status is None or status.design_doc_hash != current_hash:
        status = init_status_from_design(design_path, data)
        status.save(status_path)

    # 4. Check if any tasks are dispatched (subagents running)
    dispatched = get_dispatched_tasks(status)

    if dispatched:
        # Check if dispatched tasks have completed (new commits OR transcript evidence)
        completed = check_dispatched_tasks_complete(status)

        # Also check transcript for completion evidence
        if transcript_path:
            transcript_completed = check_transcript_for_task_completion(transcript_path, dispatched)
            for task_name in transcript_completed:
                if task_name not in completed:
                    completed.append(task_name)

        for task_name in completed:
            task = status.tasks[task_name]
            task["status"] = TaskStatus.COMPLETED.value
            # Update last_commit
            if task.get("worktree_path"):
                task["last_commit"] = get_worktree_head(Path(task["worktree_path"]))

        # If some tasks still dispatched (no new commits), wait
        still_running = [t for t in dispatched if t not in completed]
        if still_running:
            status.save(status_path)
            return {
                "decision": "block",
                "reason": f"""[Swiss Cheese] Waiting for subagents to complete...

**Still running**: {", ".join(still_running)}

The subagents are working in their worktrees. Once they commit their changes,
the orchestrator will detect completion and proceed with gate validation.

If the subagents have finished, ensure they committed their changes.
""",
            }

    # 5. Check for completed tasks that need validation
    completed_tasks = [
        name for name, task in status.tasks.items()
        if task["status"] == TaskStatus.COMPLETED.value
    ]

    if completed_tasks:
        # Run gate validation for the current layer
        gate = status.gates.get(status.current_layer, {})
        target = gate.get("target", f"validate-{status.current_layer}")

        passed, output, exit_code = run_makefile_gate(target)
        gate["output"] = output
        gate["exit_code"] = exit_code

        if passed:
            gate["status"] = GateStatus.PASSED.value
            # Mark completed tasks as passed
            for task_name in completed_tasks:
                if status.tasks[task_name]["layer"] == status.current_layer:
                    status.tasks[task_name]["status"] = TaskStatus.PASSED.value
                    # Update traceability
                    for req_id in status.tasks[task_name].get("requirements", []):
                        if req_id in status.traceability:
                            status.traceability[req_id]["status"] = "verified"

            # Rebase passed tasks back to main branch
            rebase_errors = rebase_layer_tasks(status, status.current_layer)
            if rebase_errors:
                error_msg = "\n".join(rebase_errors)
                status.save(status_path)
                return {
                    "decision": "block",
                    "reason": f"""[Swiss Cheese] Gate passed but rebase failed:

{error_msg}

Please manually resolve conflicts and merge the branches, then try again.""",
                }
        else:
            gate["status"] = GateStatus.FAILED.value
            # Mark tasks as failed, allow retry
            for task_name in completed_tasks:
                task = status.tasks[task_name]
                if task["layer"] == status.current_layer:
                    task["iteration"] += 1
                    if task["iteration"] >= status.max_iterations:
                        task["status"] = TaskStatus.FAILED.value
                        task["last_error"] = output[:500]
                    else:
                        task["status"] = TaskStatus.PENDING.value
                        task["last_error"] = output[:500]

            status.save(status_path)
            return {
                "decision": "block",
                "reason": f"""[Swiss Cheese] Gate validation FAILED for {status.current_layer}

**Makefile target**: `make {target}`
**Exit code**: {exit_code}

**Output**:
```
{output[:1500]}
```

Please fix the issues and try again. Tasks have been reset to pending for retry.
""",
            }

    # 6. Check if current layer is complete
    if all_layer_tasks_complete(status, status.current_layer):
        # Advance to next layer
        next_layer = get_next_layer(status.current_layer)
        if next_layer:
            status.current_layer = next_layer
            status.save(status_path)
            # Continue to check for ready tasks in new layer
        else:
            # All layers complete!
            report = generate_traceability_report(status)
            report_path = PROJECT_DIR / ".claude" / "traceability_matrix.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)

            return {
                "decision": "approve",
                "systemMessage": f"""[Swiss Cheese] All verification layers complete!

Traceability matrix saved to: {report_path}

**Summary**:
- Requirements: {report['summary']['total_requirements']}
- Verified: {report['summary']['verified']}
- Covered: {report['summary']['covered']}
- Pending: {report['summary']['pending']}

Ready for release decision.
""",
            }

    # 7. Get tasks ready to dispatch
    ready_tasks = get_ready_tasks(status)

    if ready_tasks:
        # Create worktrees and mark as dispatched
        for task_name in ready_tasks:
            task = status.tasks[task_name]
            worktree = create_worktree(task_name, task["branch"])
            if worktree:
                task["worktree_path"] = str(worktree)
                task["last_commit"] = get_worktree_head(worktree)
            task["status"] = TaskStatus.DISPATCHED.value

        status.iteration += 1
        status.save(status_path)

        prompt = generate_dispatch_prompt(status, ready_tasks)
        return {
            "decision": "block",
            "reason": prompt,
        }

    # 8. No tasks ready - might be waiting on dependencies
    pending = [
        name for name, task in status.tasks.items()
        if task["status"] == TaskStatus.PENDING.value
        and task["layer"] == status.current_layer
    ]

    if pending:
        status.save(status_path)
        return {
            "decision": "block",
            "reason": f"""[Swiss Cheese] Waiting on task dependencies

**Current layer**: {status.current_layer}
**Pending tasks**: {", ".join(pending)}

These tasks are waiting for their dependencies to complete.
Check the design document for dependency configuration.
""",
        }

    # Should not reach here, but approve if nothing to do
    status.save(status_path)
    return {"decision": "approve"}


def main():
    """Entry point - read stdin, route to appropriate handler, output result."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        input_data = {}

    # Route based on event type
    event_name = input_data.get("hook_event_name", "Stop")

    if event_name == "SubagentStop":
        result = handle_subagent_stop(input_data)
    else:
        # Stop event (or unknown - treat as Stop)
        result = handle_stop_event(input_data)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
