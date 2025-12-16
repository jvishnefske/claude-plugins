#!/usr/bin/env python3
"""
Swiss Cheese Orchestrator - Simplified Stop Hook Implementation

This orchestrator runs on Stop events only. It:
1. Validates TOML design documents against the schema
2. Tracks task/gate status in /tmp (invisible to agent)
3. Runs Makefile targets for gate validation
4. Generates traceability matrix from test results
5. Returns block/continue decision to keep the loop running

Similar to ralph-wiggum stop-hook but with Makefile-based gating.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from schema import validate_design_document, get_schema_for_agent, LAYERS


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class GateStatus(str, Enum):
    NOT_RUN = "not_run"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskState:
    name: str
    layer: str
    status: TaskStatus = TaskStatus.PENDING
    iteration: int = 0
    requirements: list[str] = field(default_factory=list)
    last_error: str | None = None
    passed_at: str | None = None


@dataclass
class GateState:
    name: str
    target: str
    status: GateStatus = GateStatus.NOT_RUN
    output: str | None = None
    exit_code: int | None = None
    run_at: str | None = None


@dataclass
class TraceabilityEntry:
    requirement_id: str
    task_ids: list[str] = field(default_factory=list)
    test_names: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, covered, verified


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


def get_status_file_path(project_name: str) -> Path:
    """Get status file path in /tmp based on project name."""
    # Use hash of project dir to avoid collisions
    project_hash = hashlib.md5(str(PROJECT_DIR).encode()).hexdigest()[:8]
    return Path(f"/tmp/swiss_cheese_{project_hash}.json")


def find_design_document() -> Path | None:
    """Find TOML design document in common locations."""
    candidates = [
        PROJECT_DIR / "design.toml",
        PROJECT_DIR / "swiss-cheese.toml",
        PROJECT_DIR / "requirements.toml",
        PROJECT_DIR / ".claude" / "design.toml",
        PROJECT_DIR / "docs" / "design.toml",
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
    )

    # Initialize tasks from design
    for task_name, task in data.get("tasks", {}).items():
        status.tasks[task_name] = {
            "name": task_name,
            "layer": task["layer"],
            "status": TaskStatus.PENDING.value,
            "iteration": 0,
            "requirements": task.get("requirements", []),
            "last_error": None,
            "passed_at": None,
        }

    # Initialize gates from layers
    for layer_name, layer_info in LAYERS.items():
        status.gates[layer_name] = {
            "name": layer_name,
            "target": layer_info["makefile_target"],
            "status": GateStatus.NOT_RUN.value,
            "output": None,
            "exit_code": None,
            "run_at": None,
        }

    # Initialize traceability from requirements
    for req in data.get("requirements", []):
        req_id = req.get("id")
        if req_id:
            # Find tasks that reference this requirement
            task_ids = [
                name for name, task in data.get("tasks", {}).items()
                if req_id in task.get("requirements", [])
            ]
            status.traceability[req_id] = {
                "requirement_id": req_id,
                "task_ids": task_ids,
                "test_names": [],
                "status": "pending",
            }

    return status


def run_makefile_gate(gate_name: str, target: str) -> tuple[bool, str, int]:
    """Run a Makefile target for gate validation."""
    makefile_path = PROJECT_DIR / "Makefile"
    if not makefile_path.exists():
        return False, "No Makefile found in project root", 1

    try:
        result = subprocess.run(
            ["make", target],
            cwd=PROJECT_DIR,
            capture_output=True,
            timeout=600,  # 10 minute timeout
        )
        output = result.stdout.decode() + result.stderr.decode()
        return result.returncode == 0, output[-2000:], result.returncode  # Truncate output
    except subprocess.TimeoutExpired:
        return False, "Gate validation timed out after 10 minutes", -1
    except FileNotFoundError:
        return False, "make command not found", -1
    except Exception as e:
        return False, str(e), -1


def get_current_layer_tasks(status: OrchestratorStatus) -> list[str]:
    """Get tasks in the current layer that need work."""
    return [
        name for name, task in status.tasks.items()
        if task["layer"] == status.current_layer
        and task["status"] in (TaskStatus.PENDING.value, TaskStatus.FAILED.value)
        and task["iteration"] < status.max_iterations
    ]


def all_layer_tasks_complete(status: OrchestratorStatus, layer: str) -> bool:
    """Check if all tasks in a layer are complete."""
    layer_tasks = [t for t in status.tasks.values() if t["layer"] == layer]
    if not layer_tasks:
        return True  # No tasks in this layer
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


def check_layer_dependencies(status: OrchestratorStatus, layer: str) -> bool:
    """Check if all dependency layers have passed their gates."""
    layer_info = LAYERS.get(layer, {})
    deps = layer_info.get("depends_on", [])
    for dep in deps:
        gate = status.gates.get(dep, {})
        if gate.get("status") != GateStatus.PASSED.value:
            return False
    return True


def update_traceability_from_tests(status: OrchestratorStatus) -> None:
    """Update traceability matrix from test output files."""
    # Look for test result files
    test_files = [
        PROJECT_DIR / "target" / "test-results.json",
        PROJECT_DIR / "test-results.json",
        PROJECT_DIR / "coverage.json",
    ]

    for test_file in test_files:
        if not test_file.exists():
            continue
        try:
            with open(test_file) as f:
                test_data = json.load(f)

            # Extract test names and try to match to requirements
            # Convention: test_req_001_* matches REQ-001
            for test_name in extract_test_names(test_data):
                for req_id, trace in status.traceability.items():
                    # Match test names to requirements
                    req_num = req_id.replace("REQ-", "").lower()
                    if f"req_{req_num}" in test_name.lower() or f"req{req_num}" in test_name.lower():
                        if test_name not in trace["test_names"]:
                            trace["test_names"].append(test_name)
                        trace["status"] = "covered"
        except (json.JSONDecodeError, KeyError):
            continue


def extract_test_names(test_data: dict) -> list[str]:
    """Extract test names from various test result formats."""
    names = []

    # Cargo test JSON format
    if "tests" in test_data:
        for test in test_data["tests"]:
            if "name" in test:
                names.append(test["name"])

    # LLVM-cov format
    if "data" in test_data:
        for item in test_data.get("data", []):
            for func in item.get("functions", []):
                if func.get("name", "").startswith("test_"):
                    names.append(func["name"])

    # Generic: look for any "name" field containing "test"
    def find_tests(obj, depth=0):
        if depth > 10:
            return
        if isinstance(obj, dict):
            if "name" in obj and "test" in str(obj["name"]).lower():
                names.append(obj["name"])
            for v in obj.values():
                find_tests(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                find_tests(item, depth + 1)

    find_tests(test_data)
    return list(set(names))


def generate_traceability_report(status: OrchestratorStatus) -> dict:
    """Generate traceability matrix report."""
    report = {
        "project": status.project_name,
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_requirements": len(status.traceability),
            "covered": 0,
            "verified": 0,
            "pending": 0,
        },
        "matrix": [],
    }

    for req_id, trace in status.traceability.items():
        entry = {
            "requirement_id": req_id,
            "tasks": trace["task_ids"],
            "tests": trace["test_names"],
            "status": trace["status"],
        }
        report["matrix"].append(entry)

        # Update summary counts
        if trace["status"] == "verified":
            report["summary"]["verified"] += 1
        elif trace["status"] == "covered":
            report["summary"]["covered"] += 1
        else:
            report["summary"]["pending"] += 1

    return report


def build_continue_prompt(status: OrchestratorStatus, pending_tasks: list[str], gate_failed: bool = False) -> str:
    """Build the prompt to continue orchestration."""
    layer_info = LAYERS.get(status.current_layer, {})

    prompt = f"""## [Swiss Cheese] Orchestration Iteration {status.iteration + 1}

**Current Layer**: {status.current_layer} - {layer_info.get('description', '')}
**Design Document**: {status.design_doc_path}

"""

    if gate_failed:
        gate = status.gates.get(status.current_layer, {})
        prompt += f"""### Gate Validation Failed

The `{gate.get('target')}` Makefile target failed (exit code: {gate.get('exit_code')}).

**Output**:
```
{gate.get('output', 'No output captured')[:1500]}
```

Please fix the issues and ensure the gate passes before proceeding.

"""

    if pending_tasks:
        prompt += f"""### Pending Tasks in {status.current_layer} layer

The following tasks need to be completed:

"""
        for task_name in pending_tasks:
            task = status.tasks[task_name]
            prompt += f"- **{task_name}**: {task.get('description', 'No description')}"
            if task["last_error"]:
                prompt += f" (Previous error: {task['last_error'][:200]})"
            prompt += "\n"

        prompt += """
Work on these tasks and mark them complete. When done, the orchestrator will run the layer's gate validation.
"""
    else:
        prompt += f"""### Ready for Gate Validation

All tasks in the {status.current_layer} layer are complete. Run `make {layer_info.get('makefile_target')}` to validate.
"""

    return prompt


def handle_stop_event(input_data: dict) -> dict:
    """Main Stop event handler - orchestration logic."""

    # 1. Find design document
    design_path = find_design_document()
    if design_path is None:
        # No design document - allow stop, no orchestration needed
        return {"decision": "approve"}

    # 2. Parse and validate design document
    try:
        data, validation = parse_design_document(design_path)
    except Exception as e:
        # Invalid TOML - block and ask for fix
        return {
            "decision": "block",
            "reason": f"[Swiss Cheese] Invalid design document: {e}\n\nPlease fix the TOML syntax.",
        }

    if not validation.valid:
        # Schema validation failed - provide schema and ask for fix
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

    # Check if design doc changed
    current_hash = compute_file_hash(design_path)
    if status is None or status.design_doc_hash != current_hash:
        # New or changed design doc - reinitialize
        status = init_status_from_design(design_path, data)
        status.save(status_path)

    # 4. Update traceability from any test results
    update_traceability_from_tests(status)

    # 5. Check current layer status
    current_layer = status.current_layer

    # Check if we can proceed with this layer (dependencies met)
    if not check_layer_dependencies(status, current_layer):
        deps = LAYERS.get(current_layer, {}).get("depends_on", [])
        return {
            "decision": "block",
            "reason": f"[Swiss Cheese] Cannot proceed with {current_layer} - dependencies not met: {deps}",
        }

    # 6. Get pending tasks in current layer
    pending_tasks = get_current_layer_tasks(status)

    # 7. If tasks pending, block and continue work
    if pending_tasks:
        status.iteration += 1
        status.save(status_path)
        prompt = build_continue_prompt(status, pending_tasks)
        return {
            "decision": "block",
            "reason": prompt,
        }

    # 8. All tasks in layer complete - run gate validation
    if all_layer_tasks_complete(status, current_layer):
        gate = status.gates.get(current_layer, {})

        # Only run gate if not already passed
        if gate.get("status") != GateStatus.PASSED.value:
            gate["status"] = GateStatus.RUNNING.value
            gate["run_at"] = datetime.now().isoformat()
            status.save(status_path)

            passed, output, exit_code = run_makefile_gate(current_layer, gate["target"])

            gate["output"] = output
            gate["exit_code"] = exit_code

            if passed:
                gate["status"] = GateStatus.PASSED.value

                # Mark requirements in this layer as verified
                for task in status.tasks.values():
                    if task["layer"] == current_layer:
                        for req_id in task.get("requirements", []):
                            if req_id in status.traceability:
                                status.traceability[req_id]["status"] = "verified"
            else:
                gate["status"] = GateStatus.FAILED.value
                status.save(status_path)

                # Reset tasks to allow retry
                for task_name, task in status.tasks.items():
                    if task["layer"] == current_layer and task["status"] == TaskStatus.PASSED.value:
                        if task["iteration"] < status.max_iterations:
                            task["status"] = TaskStatus.PENDING.value

                prompt = build_continue_prompt(status, get_current_layer_tasks(status), gate_failed=True)
                return {
                    "decision": "block",
                    "reason": prompt,
                }

        # Gate passed - move to next layer
        next_layer = get_next_layer(current_layer)
        if next_layer:
            # Check if next layer is optional and should be skipped
            if LAYERS.get(next_layer, {}).get("optional", False):
                # For now, proceed - user can skip via command
                pass

            status.current_layer = next_layer
            status.save(status_path)

            pending = get_current_layer_tasks(status)
            if pending:
                prompt = build_continue_prompt(status, pending)
                return {
                    "decision": "block",
                    "reason": prompt,
                }

    # 9. Check if all gates passed (orchestration complete)
    all_required_passed = all(
        status.gates.get(layer, {}).get("status") == GateStatus.PASSED.value
        for layer in LAYERS
        if not LAYERS[layer].get("optional", False)
    )

    if all_required_passed:
        # Generate final traceability report
        report = generate_traceability_report(status)
        report_path = PROJECT_DIR / ".claude" / "traceability_matrix.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        return {
            "decision": "approve",
            "systemMessage": f"""[Swiss Cheese] Orchestration Complete!

All verification gates passed. Traceability matrix saved to: {report_path}

**Summary**:
- Requirements: {report['summary']['total_requirements']}
- Verified: {report['summary']['verified']}
- Covered: {report['summary']['covered']}
- Pending: {report['summary']['pending']}
""",
        }

    # Still work to do
    status.iteration += 1
    status.save(status_path)
    pending = get_current_layer_tasks(status)
    prompt = build_continue_prompt(status, pending)
    return {
        "decision": "block",
        "reason": prompt,
    }


def main():
    """Entry point - read stdin, process Stop event, output decision."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        input_data = {}

    result = handle_stop_event(input_data)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
