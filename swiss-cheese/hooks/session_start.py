#!/usr/bin/env python3
"""
SessionStart hook - validates TOML task spec and provides ready tasks with worktree context.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11


@dataclass
class Project:
    """Project metadata."""
    name: str
    description: str = ""
    worktree_base: str = ".worktrees"


@dataclass
class Task:
    """Task definition with validation."""
    id: str
    title: str
    acceptance: str
    status: str = "pending"
    deps: list[str] = field(default_factory=list)
    spec_file: Optional[str] = None
    worktree: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Task must have an id")
        if not self.title:
            raise ValueError(f"Task {self.id} must have a title")
        if not self.acceptance:
            raise ValueError(f"Task {self.id} must have acceptance criteria")
        if self.status not in ("pending", "in_progress", "complete"):
            raise ValueError(f"Task {self.id} has invalid status: {self.status}")


@dataclass
class TaskSpec:
    """Full task specification schema."""
    version: int
    status: str
    project: Project
    tasks: list[Task]

    def __post_init__(self) -> None:
        if self.version != 1:
            raise ValueError(f"Unsupported spec version: {self.version}")
        if self.status not in ("draft", "needs_review", "ready_for_implementation"):
            raise ValueError(f"Invalid spec status: {self.status}")

        # Validate all task deps reference existing tasks
        task_ids = {t.id for t in self.tasks}
        for task in self.tasks:
            for dep in task.deps:
                if dep not in task_ids:
                    raise ValueError(f"Task {task.id} depends on unknown task: {dep}")


def load_input() -> dict[str, Any]:
    """Load hook input from stdin."""
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}


def block(reason: str) -> None:
    """Output block decision and exit."""
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def allow(reason: str = "") -> None:
    """Output allow decision and exit."""
    print(json.dumps({"decision": "allow", "reason": reason}))
    sys.exit(0)


def parse_spec(toml_path: Path) -> TaskSpec:
    """Parse and validate TOML spec into dataclasses."""
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    project_data = data.get("project", {})
    project = Project(
        name=project_data.get("name", ""),
        description=project_data.get("description", ""),
        worktree_base=project_data.get("worktree_base", ".worktrees"),
    )

    tasks = []
    for t in data.get("tasks", []):
        tasks.append(Task(
            id=t.get("id", ""),
            title=t.get("title", ""),
            acceptance=t.get("acceptance", ""),
            status=t.get("status", "pending"),
            deps=t.get("deps", []),
            spec_file=t.get("spec_file"),
            worktree=t.get("worktree"),
        ))

    return TaskSpec(
        version=data.get("version", 1),
        status=data.get("status", "draft"),
        project=project,
        tasks=tasks,
    )


def topological_sort(tasks: list[Task]) -> list[Task]:
    """Kahn's algorithm for topological sort. Returns tasks in dependency order."""
    # Build adjacency and in-degree
    task_map = {t.id: t for t in tasks}
    in_degree: dict[str, int] = {t.id: 0 for t in tasks}
    dependents: dict[str, list[str]] = {t.id: [] for t in tasks}

    for task in tasks:
        for dep in task.deps:
            if dep in task_map:
                dependents[dep].append(task.id)
                in_degree[task.id] += 1

    # Start with nodes that have no dependencies
    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    sorted_ids: list[str] = []

    while queue:
        current = queue.pop(0)
        sorted_ids.append(current)

        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Check for cycle
    if len(sorted_ids) != len(tasks):
        cycle_tasks = [tid for tid in in_degree if in_degree[tid] > 0]
        raise ValueError(f"Dependency cycle detected involving: {cycle_tasks}")

    return [task_map[tid] for tid in sorted_ids]


def get_ready_tasks(tasks: list[Task]) -> list[Task]:
    """Return pending tasks whose dependencies are all complete."""
    complete_ids = {t.id for t in tasks if t.status == "complete"}

    ready = []
    for task in tasks:
        if task.status != "pending":
            continue
        if all(dep in complete_ids for dep in task.deps):
            ready.append(task)

    return ready


def get_worktree_path(project_dir: Path, spec: TaskSpec, task: Task) -> Path:
    """Get or create worktree path for a task."""
    if task.worktree:
        return project_dir / task.worktree

    worktree_base = project_dir / spec.project.worktree_base
    return worktree_base / task.id


def list_worktrees(project_dir: Path) -> dict[str, str]:
    """List git worktrees and their branches."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return {}

        worktrees = {}
        current_path = None
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                current_path = line[9:]
            elif line.startswith("branch ") and current_path:
                worktrees[current_path] = line[7:]
                current_path = None

        return worktrees
    except Exception:
        return {}


def format_task_context(task: Task, worktree_path: Path, spec_content: Optional[str]) -> str:
    """Format task context for the agent."""
    lines = [
        f"### {task.id}: {task.title}",
        f"**Worktree:** `{worktree_path}`",
        f"**Acceptance:** {task.acceptance}",
    ]

    if task.deps:
        lines.append(f"**Dependencies:** {', '.join(task.deps)}")

    if spec_content:
        lines.append(f"\n**Specification:**\n{spec_content}")

    return "\n".join(lines)


def main() -> None:
    input_data = load_input()
    project_dir = Path(input_data.get("project_dir", ".")).resolve()
    spec_file = project_dir / ".claude" / "tasks.toml"

    # No spec file - request design phase
    if not spec_file.exists():
        block(
            "No task specification found. Run `/swiss-cheese:design` to create `.claude/tasks.toml`:\n\n"
            "```toml\n"
            "version = 1\n"
            "status = \"ready_for_implementation\"\n\n"
            "[project]\n"
            "name = \"my-project\"\n"
            "worktree_base = \".worktrees\"\n\n"
            "[[tasks]]\n"
            "id = \"task-001\"\n"
            "title = \"Implement feature X\"\n"
            "acceptance = \"Tests pass, no warnings\"\n"
            "deps = []\n"
            "status = \"pending\"\n"
            "```"
        )

    # Parse and validate spec
    try:
        spec = parse_spec(spec_file)
    except (tomllib.TOMLDecodeError, ValueError) as e:
        block(f"Invalid tasks.toml: {e}")

    if spec.status != "ready_for_implementation":
        block(f"Spec status is '{spec.status}'. Complete design phase first.")

    if not spec.tasks:
        block("No tasks defined in tasks.toml")

    # Topological sort to detect cycles and get execution order
    try:
        sorted_tasks = topological_sort(spec.tasks)
    except ValueError as e:
        block(str(e))

    # Check completion
    pending = [t for t in sorted_tasks if t.status == "pending"]
    in_progress = [t for t in sorted_tasks if t.status == "in_progress"]

    if not pending and not in_progress:
        allow("All tasks complete.")

    # Find ready tasks
    ready = get_ready_tasks(sorted_tasks)

    if not ready and not in_progress:
        block(
            "No tasks ready - dependency cycle or all deps incomplete.\n"
            f"Pending: {[t.id for t in pending]}"
        )

    # Get worktree info
    _worktrees = list_worktrees(project_dir)

    # Build task contexts
    task_contexts = []

    for task in in_progress:
        worktree_path = get_worktree_path(project_dir, spec, task)
        spec_content = None
        if task.spec_file:
            spec_path = project_dir / task.spec_file
            if spec_path.exists():
                spec_content = spec_path.read_text()
        task_contexts.append(("IN PROGRESS", format_task_context(task, worktree_path, spec_content)))

    for task in ready:
        worktree_path = get_worktree_path(project_dir, spec, task)
        spec_content = None
        if task.spec_file:
            spec_path = project_dir / task.spec_file
            if spec_path.exists():
                spec_content = spec_path.read_text()
        task_contexts.append(("READY", format_task_context(task, worktree_path, spec_content)))

    # Format output
    output_parts = ["## Implementation Tasks\n"]

    for status, context in task_contexts:
        output_parts.append(f"**[{status}]**\n{context}\n")

    output_parts.append(
        "\n## Workflow\n"
        "1. Create worktree: `git worktree add <path> -b <task-id>`\n"
        "2. Update task status to `in_progress` in tasks.toml\n"
        "3. TDD: Write failing test → Implement → Refactor\n"
        "4. Run `make verify` (must pass without warnings)\n"
        "5. Update task status to `complete`\n"
    )

    block("\n".join(output_parts))


if __name__ == "__main__":
    main()
