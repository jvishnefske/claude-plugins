"""Unit tests for orchestrate.py - Swiss Cheese orchestrator logic.

These tests do not require any API keys. They test the orchestration logic
using mocks for filesystem and git operations.
"""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add hooks directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from orchestrate import (
    TaskStatus,
    GateStatus,
    OrchestratorStatus,
    get_status_file_path,
    compute_file_hash,
    init_status_from_design,
    get_ready_tasks,
    get_dispatched_tasks,
    all_layer_tasks_complete,
    get_next_layer,
    build_task_invocation,
    generate_dispatch_prompt,
    generate_traceability_report,
    identify_task_from_subagent,
)


class TestTaskStatus:
    """Test TaskStatus enum."""

    def test_status_values(self):
        """Verify all expected status values exist."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.DISPATCHED.value == "dispatched"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.PASSED.value == "passed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.SKIPPED.value == "skipped"


class TestGateStatus:
    """Test GateStatus enum."""

    def test_status_values(self):
        """Verify all expected status values exist."""
        assert GateStatus.NOT_RUN.value == "not_run"
        assert GateStatus.PASSED.value == "passed"
        assert GateStatus.FAILED.value == "failed"
        assert GateStatus.SKIPPED.value == "skipped"


class TestOrchestratorStatus:
    """Test OrchestratorStatus dataclass."""

    def test_create_minimal_status(self):
        """Create a minimal status object."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path/to/doc.toml",
            design_doc_hash="abc123",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
            current_layer="requirements",
        )
        assert status.project_name == "test"
        assert status.tasks == {}
        assert status.gates == {}
        assert status.iteration == 0
        assert status.max_iterations == 5
        assert status.max_parallel == 4

    def test_save_and_load(self):
        """Test save and load round-trip."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path/to/doc.toml",
            design_doc_hash="abc123",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
            current_layer="implementation",
            tasks={"task1": {"status": "pending"}},
            iteration=2,
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            status.save(path)
            loaded = OrchestratorStatus.load(path)

            assert loaded is not None
            assert loaded.project_name == "test"
            assert loaded.current_layer == "implementation"
            assert loaded.tasks == {"task1": {"status": "pending"}}
            assert loaded.iteration == 2
            # updated_at should have changed on save
            assert loaded.updated_at != "2024-01-01T00:00:00"
        finally:
            path.unlink()

    def test_load_nonexistent_returns_none(self):
        """Load from nonexistent file returns None."""
        result = OrchestratorStatus.load(Path("/nonexistent/path.json"))
        assert result is None

    def test_load_invalid_json_returns_none(self):
        """Load from invalid JSON returns None."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("not valid json")
            path = Path(f.name)

        try:
            result = OrchestratorStatus.load(path)
            assert result is None
        finally:
            path.unlink()


class TestGetStatusFilePath:
    """Test get_status_file_path function."""

    @patch("orchestrate.PROJECT_DIR", Path("/home/user/myproject"))
    def test_generates_path_in_tmp(self):
        """Status file should be in /tmp."""
        path = get_status_file_path("myproject")
        assert str(path).startswith("/tmp/swiss_cheese_")
        assert str(path).endswith(".json")

    @patch("orchestrate.PROJECT_DIR", Path("/home/user/myproject"))
    def test_consistent_for_same_project(self):
        """Same project dir should get same status path."""
        path1 = get_status_file_path("project1")
        path2 = get_status_file_path("project2")
        # Different project names don't affect path (path is based on PROJECT_DIR hash)
        assert path1 == path2


class TestComputeFileHash:
    """Test compute_file_hash function."""

    def test_hash_consistency(self):
        """Same content should produce same hash."""
        with tempfile.NamedTemporaryFile(delete=False, mode="w") as f:
            f.write("test content")
            path = Path(f.name)

        try:
            hash1 = compute_file_hash(path)
            hash2 = compute_file_hash(path)
            assert hash1 == hash2
            assert len(hash1) == 32  # MD5 hex digest length
        finally:
            path.unlink()

    def test_different_content_different_hash(self):
        """Different content should produce different hashes."""
        with tempfile.NamedTemporaryFile(delete=False, mode="w") as f1:
            f1.write("content1")
            path1 = Path(f1.name)

        with tempfile.NamedTemporaryFile(delete=False, mode="w") as f2:
            f2.write("content2")
            path2 = Path(f2.name)

        try:
            hash1 = compute_file_hash(path1)
            hash2 = compute_file_hash(path2)
            assert hash1 != hash2
        finally:
            path1.unlink()
            path2.unlink()


class TestInitStatusFromDesign:
    """Test init_status_from_design function."""

    def test_basic_initialization(self):
        """Test basic status initialization from design doc."""
        design_path = Path("/tmp/test_design.toml")
        design_path.write_text("[project]\nname = 'test'\nversion = '1.0.0'")

        try:
            data = {
                "project": {
                    "name": "test-project",
                    "version": "1.0.0",
                    "max_iterations": 10,
                    "max_parallel_agents": 2,
                },
                "requirements": [
                    {"id": "REQ-001", "title": "Test requirement"},
                ],
                "tasks": {
                    "task1": {
                        "layer": "implementation",
                        "description": "Implement feature",
                        "requirements": ["REQ-001"],
                    },
                },
            }

            status = init_status_from_design(design_path, data)

            assert status.project_name == "test-project"
            assert status.current_layer == "requirements"
            assert status.max_iterations == 10
            assert status.max_parallel == 2
            assert "task1" in status.tasks
            assert status.tasks["task1"]["layer"] == "implementation"
            assert status.tasks["task1"]["status"] == TaskStatus.PENDING.value
            assert "REQ-001" in status.traceability
        finally:
            design_path.unlink()

    def test_gate_initialization(self):
        """Test that gates are initialized from LAYERS."""
        design_path = Path("/tmp/test_design2.toml")
        design_path.write_text("[project]\nname = 'test'\nversion = '1.0.0'")

        try:
            data = {
                "project": {"name": "test", "version": "1.0.0"},
                "requirements": [],
                "tasks": {},
            }

            status = init_status_from_design(design_path, data)

            # Should have gates for all layers
            assert "requirements" in status.gates
            assert "implementation" in status.gates
            assert "safety" in status.gates
            assert all(
                g["status"] == GateStatus.NOT_RUN.value for g in status.gates.values()
            )
        finally:
            design_path.unlink()


class TestGetReadyTasks:
    """Test get_ready_tasks function."""

    def test_no_tasks_returns_empty(self):
        """No tasks means no ready tasks."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={},
        )
        assert get_ready_tasks(status) == []

    def test_pending_task_in_current_layer_is_ready(self):
        """Pending task in current layer should be ready."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {
                    "layer": "implementation",
                    "status": TaskStatus.PENDING.value,
                    "depends_on": [],
                },
            },
        )
        assert get_ready_tasks(status) == ["task1"]

    def test_task_in_different_layer_not_ready(self):
        """Task in different layer should not be ready."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {
                    "layer": "architecture",  # Different layer
                    "status": TaskStatus.PENDING.value,
                    "depends_on": [],
                },
            },
        )
        assert get_ready_tasks(status) == []

    def test_dispatched_task_not_ready(self):
        """Already dispatched task should not be ready."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {
                    "layer": "implementation",
                    "status": TaskStatus.DISPATCHED.value,
                    "depends_on": [],
                },
            },
        )
        assert get_ready_tasks(status) == []

    def test_task_with_unsatisfied_dependency_not_ready(self):
        """Task with pending dependency should not be ready."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {
                    "layer": "implementation",
                    "status": TaskStatus.PENDING.value,
                    "depends_on": ["task2"],
                },
                "task2": {
                    "layer": "implementation",
                    "status": TaskStatus.PENDING.value,
                    "depends_on": [],
                },
            },
        )
        ready = get_ready_tasks(status)
        assert "task1" not in ready
        assert "task2" in ready

    def test_task_with_passed_dependency_is_ready(self):
        """Task with passed dependency should be ready."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {
                    "layer": "implementation",
                    "status": TaskStatus.PENDING.value,
                    "depends_on": ["task2"],
                },
                "task2": {
                    "layer": "implementation",
                    "status": TaskStatus.PASSED.value,
                    "depends_on": [],
                },
            },
        )
        ready = get_ready_tasks(status)
        assert "task1" in ready

    def test_respects_max_parallel(self):
        """Should limit ready tasks to max_parallel."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            max_parallel=2,  # Only 2 at a time
            tasks={
                "task1": {
                    "layer": "implementation",
                    "status": TaskStatus.PENDING.value,
                    "depends_on": [],
                },
                "task2": {
                    "layer": "implementation",
                    "status": TaskStatus.PENDING.value,
                    "depends_on": [],
                },
                "task3": {
                    "layer": "implementation",
                    "status": TaskStatus.PENDING.value,
                    "depends_on": [],
                },
            },
        )
        ready = get_ready_tasks(status)
        assert len(ready) == 2


class TestGetDispatchedTasks:
    """Test get_dispatched_tasks function."""

    def test_returns_dispatched_tasks(self):
        """Should return all dispatched tasks."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {"status": TaskStatus.DISPATCHED.value},
                "task2": {"status": TaskStatus.PENDING.value},
                "task3": {"status": TaskStatus.DISPATCHED.value},
            },
        )
        dispatched = get_dispatched_tasks(status)
        assert set(dispatched) == {"task1", "task3"}

    def test_empty_when_none_dispatched(self):
        """Should return empty when no tasks dispatched."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {"status": TaskStatus.PENDING.value},
                "task2": {"status": TaskStatus.PASSED.value},
            },
        )
        assert get_dispatched_tasks(status) == []


class TestAllLayerTasksComplete:
    """Test all_layer_tasks_complete function."""

    def test_empty_layer_is_complete(self):
        """Layer with no tasks is complete."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {"layer": "architecture", "status": TaskStatus.PASSED.value},
            },
        )
        assert all_layer_tasks_complete(status, "implementation") is True

    def test_all_passed_is_complete(self):
        """Layer with all passed tasks is complete."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {"layer": "implementation", "status": TaskStatus.PASSED.value},
                "task2": {"layer": "implementation", "status": TaskStatus.PASSED.value},
            },
        )
        assert all_layer_tasks_complete(status, "implementation") is True

    def test_skipped_counts_as_complete(self):
        """Skipped tasks count as complete."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {"layer": "implementation", "status": TaskStatus.PASSED.value},
                "task2": {"layer": "implementation", "status": TaskStatus.SKIPPED.value},
            },
        )
        assert all_layer_tasks_complete(status, "implementation") is True

    def test_pending_is_not_complete(self):
        """Layer with pending tasks is not complete."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {"layer": "implementation", "status": TaskStatus.PASSED.value},
                "task2": {"layer": "implementation", "status": TaskStatus.PENDING.value},
            },
        )
        assert all_layer_tasks_complete(status, "implementation") is False


class TestGetNextLayer:
    """Test get_next_layer function."""

    def test_requirements_to_architecture(self):
        """Requirements layer should advance to architecture."""
        assert get_next_layer("requirements") == "architecture"

    def test_architecture_to_tdd(self):
        """Architecture layer should advance to tdd."""
        assert get_next_layer("architecture") == "tdd"

    def test_safety_has_no_next(self):
        """Safety is the last layer, should return None."""
        assert get_next_layer("safety") is None

    def test_invalid_layer_returns_none(self):
        """Invalid layer should return None."""
        assert get_next_layer("invalid") is None


class TestBuildTaskInvocation:
    """Test build_task_invocation function."""

    def test_generates_task_prompt(self):
        """Should generate a task invocation prompt."""
        task = {
            "layer": "implementation",
            "description": "Implement the parser",
            "requirements": ["REQ-001", "REQ-002"],
            "agent": "general-purpose",
            "worktree_path": ".worktrees/parser",
        }
        result = build_task_invocation("parser", task)

        assert "parser" in result
        assert "implementation" in result
        assert "Implement the parser" in result
        assert "REQ-001" in result
        assert ".worktrees/parser" in result
        assert "general-purpose" in result

    def test_handles_missing_requirements(self):
        """Should handle task with no requirements."""
        task = {
            "layer": "implementation",
            "description": "Simple task",
            "requirements": [],
            "agent": "general-purpose",
        }
        result = build_task_invocation("simple", task)
        assert "None" in result or "requirements" in result.lower()


class TestGenerateDispatchPrompt:
    """Test generate_dispatch_prompt function."""

    def test_generates_dispatch_prompt(self):
        """Should generate prompt for dispatching multiple tasks."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "task1": {
                    "layer": "implementation",
                    "description": "First task",
                    "requirements": [],
                    "agent": "general-purpose",
                },
                "task2": {
                    "layer": "implementation",
                    "description": "Second task",
                    "requirements": [],
                    "agent": "general-purpose",
                },
            },
        )
        prompt = generate_dispatch_prompt(status, ["task1", "task2"])

        assert "task1" in prompt
        assert "task2" in prompt
        assert "implementation" in prompt
        assert "parallel" in prompt.lower()
        assert "2" in prompt  # 2 tasks


class TestGenerateTraceabilityReport:
    """Test generate_traceability_report function."""

    def test_generates_report(self):
        """Should generate a traceability report."""
        status = OrchestratorStatus(
            project_name="test-project",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            traceability={
                "REQ-001": {
                    "requirement_id": "REQ-001",
                    "title": "User login",
                    "task_ids": ["impl_login"],
                    "test_names": ["test_login"],
                    "status": "verified",
                },
                "REQ-002": {
                    "requirement_id": "REQ-002",
                    "title": "User dashboard",
                    "task_ids": [],
                    "test_names": [],
                    "status": "pending",
                },
            },
        )

        report = generate_traceability_report(status)

        assert report["project"] == "test-project"
        assert "generated_at" in report
        assert report["summary"]["total_requirements"] == 2
        assert report["summary"]["verified"] == 1
        assert report["summary"]["pending"] == 1
        assert len(report["matrix"]) == 2


class TestIdentifyTaskFromSubagent:
    """Test identify_task_from_subagent function."""

    def test_direct_match_on_task_description(self):
        """Should match task by description."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "impl_parser": {
                    "status": TaskStatus.DISPATCHED.value,
                    "description": "Implement parser",
                },
            },
        )
        input_data = {"task_description": "impl_parser"}
        result = identify_task_from_subagent(input_data, status)
        assert result == "impl_parser"

    def test_no_match_returns_none(self):
        """Should return None when no match found."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "impl_parser": {
                    "status": TaskStatus.DISPATCHED.value,
                    "description": "Implement parser",
                },
            },
        )
        input_data = {"task_description": "unrelated_task"}
        result = identify_task_from_subagent(input_data, status)
        assert result is None

    def test_match_by_result_content(self):
        """Should match task by swiss-cheese marker in result."""
        status = OrchestratorStatus(
            project_name="test",
            design_doc_path="/path",
            design_doc_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            current_layer="implementation",
            tasks={
                "impl_parser": {
                    "status": TaskStatus.DISPATCHED.value,
                    "description": "Implement parser",
                },
            },
        )
        input_data = {
            "task_description": "something else",
            "result": "Done! Committed with [swiss-cheese] impl_parser",
        }
        result = identify_task_from_subagent(input_data, status)
        assert result == "impl_parser"
