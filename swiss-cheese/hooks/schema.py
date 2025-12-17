#!/usr/bin/env python3
"""
TOML Schema definition and validation for Swiss Cheese design documents.

This schema is provided to the agent for document creation and validated
when the agent returns a design document.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Schema as a dictionary that can be serialized to show the agent
DESIGN_DOCUMENT_SCHEMA = {
    "project": {
        "_required": True,
        "_description": "Project metadata and orchestration settings",
        "name": {"type": "string", "required": True, "description": "Project name"},
        "version": {"type": "string", "required": True, "description": "Semantic version"},
        "description": {"type": "string", "required": False, "description": "Project description"},
        "max_iterations": {"type": "integer", "required": False, "default": 5, "description": "Max retries per task"},
        "max_parallel_agents": {"type": "integer", "required": False, "default": 4, "description": "Max concurrent subagents"},
    },
    "requirements": {
        "_required": True,
        "_description": "List of requirements with unique IDs",
        "_is_array": True,
        "_item_schema": {
            "id": {"type": "string", "required": True, "pattern": r"^REQ-\d+$", "description": "Requirement ID (e.g., REQ-001)"},
            "title": {"type": "string", "required": True, "description": "Short requirement title"},
            "description": {"type": "string", "required": True, "description": "Detailed requirement description"},
            "priority": {"type": "string", "required": False, "enum": ["critical", "high", "medium", "low"], "default": "medium"},
            "acceptance_criteria": {"type": "array", "required": True, "description": "List of testable acceptance criteria"},
            "traces_to": {"type": "array", "required": False, "description": "IDs of related requirements or tests"},
        }
    },
    "tasks": {
        "_required": True,
        "_description": "Tasks organized by layer with dependencies",
        "_is_table": True,
        "_item_schema": {
            "layer": {"type": "string", "required": True, "enum": ["requirements", "architecture", "tdd", "implementation", "static_analysis", "formal_verification", "dynamic_analysis", "review", "safety"], "description": "Swiss Cheese layer"},
            "description": {"type": "string", "required": True, "description": "What this task accomplishes"},
            "depends_on": {"type": "array", "required": False, "default": [], "description": "Task IDs this depends on"},
            "requirements": {"type": "array", "required": False, "description": "Requirement IDs this task addresses"},
            "agent": {"type": "string", "required": False, "description": "Agent type to use"},
            "command": {"type": "string", "required": False, "description": "Validation command"},
            "branch": {"type": "string", "required": False, "description": "Git branch name"},
        }
    },
    "gates": {
        "_required": False,
        "_description": "Gate validation configurations with Makefile targets",
        "_is_table": True,
        "_item_schema": {
            "target": {"type": "string", "required": True, "description": "Makefile target name"},
            "fail_fast": {"type": "boolean", "required": False, "default": True},
            "min_coverage": {"type": "integer", "required": False, "description": "Minimum test coverage %"},
        }
    },
    "traceability": {
        "_required": False,
        "_description": "Traceability configuration",
        "enabled": {"type": "boolean", "required": False, "default": True},
        "report_formats": {"type": "array", "required": False, "default": ["json", "html"]},
        "test_pattern": {"type": "string", "required": False, "default": r"test_.*", "description": "Regex for test names"},
    }
}


# Layer definitions with their Makefile targets
LAYERS = {
    "requirements": {
        "order": 1,
        "description": "Formalize requirements with testable criteria",
        "depends_on": [],
        "makefile_target": "validate-requirements",
    },
    "architecture": {
        "order": 2,
        "description": "Design type-safe, ownership-correct architecture",
        "depends_on": ["requirements"],
        "makefile_target": "validate-architecture",
    },
    "tdd": {
        "order": 3,
        "description": "Write comprehensive tests BEFORE implementation",
        "depends_on": ["architecture"],
        "makefile_target": "validate-tdd",
    },
    "implementation": {
        "order": 4,
        "description": "Implement code to pass tests",
        "depends_on": ["tdd"],
        "makefile_target": "validate-implementation",
    },
    "static_analysis": {
        "order": 5,
        "description": "Run static analysis tools",
        "depends_on": ["implementation"],
        "makefile_target": "validate-static-analysis",
    },
    "formal_verification": {
        "order": 6,
        "description": "Prove properties with formal methods",
        "depends_on": ["static_analysis"],
        "makefile_target": "validate-formal-verification",
        "optional": True,
    },
    "dynamic_analysis": {
        "order": 7,
        "description": "Run dynamic analysis (Miri, fuzzing, coverage)",
        "depends_on": ["implementation"],
        "makefile_target": "validate-dynamic-analysis",
    },
    "review": {
        "order": 8,
        "description": "Independent code review",
        "depends_on": ["static_analysis", "dynamic_analysis"],
        "makefile_target": "validate-review",
    },
    "safety": {
        "order": 9,
        "description": "Assemble safety case for release decision",
        "depends_on": ["review", "formal_verification"],
        "makefile_target": "validate-safety-case",
    },
}


@dataclass
class ValidationError:
    path: str
    message: str
    value: Any = None


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [{"path": e.path, "message": e.message, "value": e.value} for e in self.errors],
            "warnings": self.warnings,
        }


def validate_design_document(data: dict) -> ValidationResult:
    """Validate a parsed TOML design document against the schema."""
    errors: list[ValidationError] = []
    warnings: list[str] = []

    # Check required top-level sections
    if "project" not in data:
        errors.append(ValidationError("project", "Missing required section [project]"))
    else:
        project = data["project"]
        if "name" not in project:
            errors.append(ValidationError("project.name", "Missing required field 'name'"))
        if "version" not in project:
            errors.append(ValidationError("project.version", "Missing required field 'version'"))

    # Validate requirements array
    if "requirements" not in data:
        errors.append(ValidationError("requirements", "Missing required section [[requirements]]"))
    else:
        requirements = data["requirements"]
        if not isinstance(requirements, list):
            errors.append(ValidationError("requirements", "Must be an array of requirement tables", type(requirements).__name__))
        else:
            req_ids = set()
            for i, req in enumerate(requirements):
                path = f"requirements[{i}]"
                if not isinstance(req, dict):
                    errors.append(ValidationError(path, "Each requirement must be a table"))
                    continue

                # Check required fields
                if "id" not in req:
                    errors.append(ValidationError(f"{path}.id", "Missing required field 'id'"))
                else:
                    req_id = req["id"]
                    if not isinstance(req_id, str) or not req_id.startswith("REQ-"):
                        errors.append(ValidationError(f"{path}.id", "ID must match pattern REQ-NNN", req_id))
                    elif req_id in req_ids:
                        errors.append(ValidationError(f"{path}.id", "Duplicate requirement ID", req_id))
                    else:
                        req_ids.add(req_id)

                if "title" not in req:
                    errors.append(ValidationError(f"{path}.title", "Missing required field 'title'"))
                if "description" not in req:
                    errors.append(ValidationError(f"{path}.description", "Missing required field 'description'"))
                if "acceptance_criteria" not in req:
                    errors.append(ValidationError(f"{path}.acceptance_criteria", "Missing required field 'acceptance_criteria'"))
                elif not isinstance(req.get("acceptance_criteria"), list):
                    errors.append(ValidationError(f"{path}.acceptance_criteria", "Must be an array"))

    # Validate tasks table
    if "tasks" not in data:
        errors.append(ValidationError("tasks", "Missing required section [tasks]"))
    else:
        tasks = data["tasks"]
        if not isinstance(tasks, dict):
            errors.append(ValidationError("tasks", "Must be a table of task definitions"))
        else:
            valid_layers = set(LAYERS.keys())
            task_ids = set(tasks.keys())

            for task_name, task in tasks.items():
                path = f"tasks.{task_name}"
                if not isinstance(task, dict):
                    errors.append(ValidationError(path, "Each task must be a table"))
                    continue

                # Check layer
                if "layer" not in task:
                    errors.append(ValidationError(f"{path}.layer", "Missing required field 'layer'"))
                elif task["layer"] not in valid_layers:
                    errors.append(ValidationError(f"{path}.layer", f"Invalid layer. Must be one of: {', '.join(valid_layers)}", task["layer"]))

                # Check description
                if "description" not in task:
                    errors.append(ValidationError(f"{path}.description", "Missing required field 'description'"))

                # Validate dependencies exist
                depends_on = task.get("depends_on", [])
                if not isinstance(depends_on, list):
                    errors.append(ValidationError(f"{path}.depends_on", "Must be an array"))
                else:
                    for dep in depends_on:
                        if dep not in task_ids:
                            errors.append(ValidationError(f"{path}.depends_on", f"Unknown dependency: {dep}", dep))

                # Validate requirements references exist
                req_refs = task.get("requirements", [])
                if isinstance(req_refs, list) and "requirements" in data and isinstance(data["requirements"], list):
                    valid_req_ids = {r.get("id") for r in data["requirements"] if isinstance(r, dict)}
                    for ref in req_refs:
                        if ref not in valid_req_ids:
                            warnings.append(f"{path}.requirements references unknown requirement: {ref}")

    # Validate gates if present
    if "gates" in data:
        gates = data["gates"]
        if isinstance(gates, dict):
            for gate_name, gate in gates.items():
                if isinstance(gate, dict) and "target" not in gate:
                    errors.append(ValidationError(f"gates.{gate_name}.target", "Missing required field 'target'"))

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def get_schema_for_agent() -> str:
    """Return a human-readable schema description for the agent."""
    return '''# Swiss Cheese Design Document Schema (TOML)

## Required Sections

### [project]
```toml
[project]
name = "project-name"              # Required: Project identifier
version = "0.1.0"                  # Required: Semantic version
description = "..."                # Optional: Project description
max_iterations = 5                 # Optional: Max task retries (default: 5)
max_parallel_agents = 4            # Optional: Max concurrent tasks (default: 4)
```

### [[requirements]]
Array of requirement tables. Each requirement must have:
```toml
[[requirements]]
id = "REQ-001"                     # Required: Unique ID matching REQ-NNN pattern
title = "Short title"              # Required: Brief requirement name
description = "Detailed..."        # Required: Full requirement description
priority = "high"                  # Optional: critical|high|medium|low (default: medium)
acceptance_criteria = [            # Required: Testable criteria
    "Criterion 1",
    "Criterion 2",
]
traces_to = ["REQ-002", "TST-001"] # Optional: Related requirements/tests
```

### [tasks.task_name]
Table of tasks. Each task must have:
```toml
[tasks.implement_parser]
layer = "implementation"           # Required: One of the 9 Swiss Cheese layers
description = "Parse input..."     # Required: What this task accomplishes
depends_on = ["design_parser"]     # Optional: Task dependencies (default: [])
requirements = ["REQ-001"]         # Optional: Requirements this addresses
agent = "implementation-agent"     # Optional: Agent type
command = "cargo test"             # Optional: Validation command
branch = "feature/parser"          # Optional: Git branch name
```

## Valid Layers (in order)
1. requirements - Formalize requirements with testable criteria
2. architecture - Design type-safe architecture
3. tdd - Write tests BEFORE implementation
4. implementation - Implement code to pass tests
5. static_analysis - Run Clippy, audit, deny
6. formal_verification - Prove properties (optional layer)
7. dynamic_analysis - Miri, fuzzing, coverage
8. review - Independent code review
9. safety - Assemble safety case

## Optional Sections

### [gates.gate_name]
```toml
[gates.static_analysis]
target = "validate-static"         # Required: Makefile target
fail_fast = true                   # Optional: Stop on first failure
min_coverage = 80                  # Optional: Minimum test coverage %
```

### [traceability]
```toml
[traceability]
enabled = true                     # Optional: Enable traceability (default: true)
report_formats = ["json", "html"]  # Optional: Output formats
test_pattern = "test_.*"           # Optional: Regex for test names
```
'''


if __name__ == "__main__":
    import json
    import sys
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    if len(sys.argv) < 2:
        print(get_schema_for_agent())
        sys.exit(0)

    # Validate a file
    path = sys.argv[1]
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        result = validate_design_document(data)
        print(json.dumps(result.to_dict(), indent=2))
        sys.exit(0 if result.valid else 1)
    except Exception as e:
        print(json.dumps({"valid": False, "errors": [{"path": "", "message": str(e)}]}))
        sys.exit(1)
