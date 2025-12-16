#!/usr/bin/env python3
"""
Session initialization hook for Swiss Cheese orchestrator.
Initializes state from design document if present.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from datetime import datetime


PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd()))
STATE_FILE = PROJECT_DIR / ".claude" / "orchestrator_state.json"
LEGACY_STATE_FILE = Path("/tmp/swiss_cheese_state.json")


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


def init_legacy_state():
    """Initialize legacy state file for backward compatibility with commands."""
    if LEGACY_STATE_FILE.exists():
        return  # Don't overwrite existing state

    state = {
        "layer": None,
        "files": [],
        "gates_passed": [],
        "ci_runs": [],
        "project_dir": str(PROJECT_DIR),
        "started_at": datetime.now().isoformat(),
    }

    with open(LEGACY_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        input_data = {}

    # Initialize legacy state for backward compatibility
    init_legacy_state()

    # Check for design document
    design_doc = find_design_document()

    messages = []

    if design_doc:
        messages.append(f"[Swiss Cheese] Found design document: {design_doc.name}")

        # Check if orchestrator state exists
        if not STATE_FILE.exists():
            messages.append("[Swiss Cheese] Run `/swiss-cheese:swiss-cheese` to initialize orchestration")
    else:
        messages.append("[Swiss Cheese] No design.toml found. Create one to enable orchestration.")
        messages.append("See examples/example_project.toml in the plugin for reference.")

    if messages:
        result = {"message": "\n".join(messages)}
        print(json.dumps(result))


if __name__ == "__main__":
    main()
