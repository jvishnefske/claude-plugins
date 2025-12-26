"""Unit tests for swiss-cheese hooks."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from session_start import (
    Project,
    Task,
    TaskSpec,
    parse_spec,
    topological_sort,
    get_ready_tasks,
    get_worktree_path,
)
from subagent_stop import (
    is_worktree,
    get_worktree_branch,
    get_main_branch,
    is_branch_in_linear_history,
)


class TestProject:
    """Test Project dataclass."""

    def test_project_with_defaults(self):
        """Project with minimal fields uses defaults."""
        p = Project(name="test")
        assert p.name == "test"
        assert p.description == ""
        assert p.worktree_base == ".worktrees"

    def test_project_with_all_fields(self):
        """Project with all fields set."""
        p = Project(name="test", description="A test", worktree_base="wt")
        assert p.name == "test"
        assert p.description == "A test"
        assert p.worktree_base == "wt"


class TestTask:
    """Test Task dataclass validation."""

    def test_valid_task(self):
        """Valid task passes validation."""
        t = Task(id="task-001", title="Do thing", acceptance="Tests pass")
        assert t.id == "task-001"
        assert t.status == "pending"
        assert t.deps == []

    def test_task_with_all_fields(self):
        """Task with all fields set."""
        t = Task(
            id="task-001",
            title="Do thing",
            acceptance="Tests pass",
            status="in_progress",
            deps=["task-000"],
            spec_file="specs/task.md",
            worktree=".wt/task-001",
        )
        assert t.status == "in_progress"
        assert t.deps == ["task-000"]
        assert t.spec_file == "specs/task.md"

    def test_task_missing_id_fails(self):
        """Task without id raises ValueError."""
        with pytest.raises(ValueError, match="must have an id"):
            Task(id="", title="Do thing", acceptance="Tests pass")

    def test_task_missing_title_fails(self):
        """Task without title raises ValueError."""
        with pytest.raises(ValueError, match="must have a title"):
            Task(id="task-001", title="", acceptance="Tests pass")

    def test_task_missing_acceptance_fails(self):
        """Task without acceptance raises ValueError."""
        with pytest.raises(ValueError, match="must have acceptance"):
            Task(id="task-001", title="Do thing", acceptance="")

    def test_task_invalid_status_fails(self):
        """Task with invalid status raises ValueError."""
        with pytest.raises(ValueError, match="invalid status"):
            Task(id="task-001", title="Do thing", acceptance="Tests pass", status="done")


class TestTaskSpec:
    """Test TaskSpec dataclass validation."""

    def test_valid_spec(self):
        """Valid spec passes validation."""
        project = Project(name="test")
        tasks = [Task(id="task-001", title="Do thing", acceptance="Tests pass")]
        spec = TaskSpec(version=1, status="ready_for_implementation", project=project, tasks=tasks)
        assert spec.version == 1

    def test_invalid_version_fails(self):
        """Invalid version raises ValueError."""
        project = Project(name="test")
        tasks = [Task(id="task-001", title="Do thing", acceptance="Tests pass")]
        with pytest.raises(ValueError, match="Unsupported spec version"):
            TaskSpec(version=2, status="ready_for_implementation", project=project, tasks=tasks)

    def test_invalid_status_fails(self):
        """Invalid status raises ValueError."""
        project = Project(name="test")
        tasks = [Task(id="task-001", title="Do thing", acceptance="Tests pass")]
        with pytest.raises(ValueError, match="Invalid spec status"):
            TaskSpec(version=1, status="invalid", project=project, tasks=tasks)

    def test_invalid_dep_reference_fails(self):
        """Task depending on nonexistent task raises ValueError."""
        project = Project(name="test")
        tasks = [
            Task(id="task-001", title="Do thing", acceptance="Tests pass", deps=["task-999"])
        ]
        with pytest.raises(ValueError, match="depends on unknown task"):
            TaskSpec(version=1, status="ready_for_implementation", project=project, tasks=tasks)

    def test_valid_dep_reference(self):
        """Task depending on existing task passes."""
        project = Project(name="test")
        tasks = [
            Task(id="task-001", title="First", acceptance="Tests pass"),
            Task(id="task-002", title="Second", acceptance="Tests pass", deps=["task-001"]),
        ]
        spec = TaskSpec(version=1, status="ready_for_implementation", project=project, tasks=tasks)
        assert len(spec.tasks) == 2


class TestParseSpec:
    """Test TOML parsing."""

    def test_parse_valid_toml(self):
        """Parse valid TOML file."""
        toml_content = """
version = 1
status = "ready_for_implementation"

[project]
name = "test-project"
description = "A test"
worktree_base = ".wt"

[[tasks]]
id = "task-001"
title = "First task"
acceptance = "Tests pass"
deps = []
status = "pending"

[[tasks]]
id = "task-002"
title = "Second task"
acceptance = "No warnings"
deps = ["task-001"]
status = "pending"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            spec = parse_spec(Path(f.name))

        assert spec.project.name == "test-project"
        assert spec.project.worktree_base == ".wt"
        assert len(spec.tasks) == 2
        assert spec.tasks[0].id == "task-001"
        assert spec.tasks[1].deps == ["task-001"]

    def test_parse_minimal_toml(self):
        """Parse minimal valid TOML."""
        toml_content = """
version = 1
status = "draft"

[project]
name = "minimal"

[[tasks]]
id = "task-001"
title = "Only task"
acceptance = "Done"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            spec = parse_spec(Path(f.name))

        assert spec.project.name == "minimal"
        assert spec.project.worktree_base == ".worktrees"  # default
        assert len(spec.tasks) == 1


class TestTopologicalSort:
    """Test topological sorting of tasks."""

    def test_no_deps(self):
        """Tasks with no deps maintain order."""
        tasks = [
            Task(id="a", title="A", acceptance="ok"),
            Task(id="b", title="B", acceptance="ok"),
            Task(id="c", title="C", acceptance="ok"),
        ]
        sorted_tasks = topological_sort(tasks)
        assert [t.id for t in sorted_tasks] == ["a", "b", "c"]

    def test_linear_deps(self):
        """Linear dependency chain sorts correctly."""
        tasks = [
            Task(id="c", title="C", acceptance="ok", deps=["b"]),
            Task(id="a", title="A", acceptance="ok"),
            Task(id="b", title="B", acceptance="ok", deps=["a"]),
        ]
        sorted_tasks = topological_sort(tasks)
        ids = [t.id for t in sorted_tasks]
        assert ids.index("a") < ids.index("b")
        assert ids.index("b") < ids.index("c")

    def test_diamond_deps(self):
        """Diamond dependency pattern sorts correctly."""
        tasks = [
            Task(id="d", title="D", acceptance="ok", deps=["b", "c"]),
            Task(id="b", title="B", acceptance="ok", deps=["a"]),
            Task(id="c", title="C", acceptance="ok", deps=["a"]),
            Task(id="a", title="A", acceptance="ok"),
        ]
        sorted_tasks = topological_sort(tasks)
        ids = [t.id for t in sorted_tasks]
        assert ids.index("a") < ids.index("b")
        assert ids.index("a") < ids.index("c")
        assert ids.index("b") < ids.index("d")
        assert ids.index("c") < ids.index("d")

    def test_cycle_detected(self):
        """Cycle in dependencies raises ValueError."""
        tasks = [
            Task(id="a", title="A", acceptance="ok", deps=["b"]),
            Task(id="b", title="B", acceptance="ok", deps=["a"]),
        ]
        with pytest.raises(ValueError, match="cycle detected"):
            topological_sort(tasks)

    def test_self_cycle_detected(self):
        """Self-referencing dependency raises ValueError."""
        tasks = [
            Task(id="a", title="A", acceptance="ok", deps=["a"]),
        ]
        with pytest.raises(ValueError, match="cycle detected"):
            topological_sort(tasks)

    def test_complex_cycle_detected(self):
        """Complex cycle (a->b->c->a) raises ValueError."""
        tasks = [
            Task(id="a", title="A", acceptance="ok", deps=["c"]),
            Task(id="b", title="B", acceptance="ok", deps=["a"]),
            Task(id="c", title="C", acceptance="ok", deps=["b"]),
        ]
        with pytest.raises(ValueError, match="cycle detected"):
            topological_sort(tasks)


class TestGetReadyTasks:
    """Test ready task selection."""

    def test_no_deps_all_ready(self):
        """Tasks with no deps are all ready."""
        tasks = [
            Task(id="a", title="A", acceptance="ok"),
            Task(id="b", title="B", acceptance="ok"),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 2

    def test_pending_with_complete_deps(self):
        """Pending task with complete deps is ready."""
        tasks = [
            Task(id="a", title="A", acceptance="ok", status="complete"),
            Task(id="b", title="B", acceptance="ok", deps=["a"]),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 1
        assert ready[0].id == "b"

    def test_pending_with_incomplete_deps(self):
        """Pending task with incomplete deps is not ready."""
        tasks = [
            Task(id="a", title="A", acceptance="ok", status="pending"),
            Task(id="b", title="B", acceptance="ok", deps=["a"]),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 1
        assert ready[0].id == "a"

    def test_in_progress_not_ready(self):
        """In-progress tasks are not in ready list."""
        tasks = [
            Task(id="a", title="A", acceptance="ok", status="in_progress"),
            Task(id="b", title="B", acceptance="ok"),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 1
        assert ready[0].id == "b"

    def test_complete_not_ready(self):
        """Complete tasks are not in ready list."""
        tasks = [
            Task(id="a", title="A", acceptance="ok", status="complete"),
            Task(id="b", title="B", acceptance="ok", status="complete"),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 0

    def test_multiple_deps_all_complete(self):
        """Task with multiple deps ready when all complete."""
        tasks = [
            Task(id="a", title="A", acceptance="ok", status="complete"),
            Task(id="b", title="B", acceptance="ok", status="complete"),
            Task(id="c", title="C", acceptance="ok", deps=["a", "b"]),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 1
        assert ready[0].id == "c"

    def test_multiple_deps_some_incomplete(self):
        """Task with multiple deps not ready when some incomplete."""
        tasks = [
            Task(id="a", title="A", acceptance="ok", status="complete"),
            Task(id="b", title="B", acceptance="ok", status="pending"),
            Task(id="c", title="C", acceptance="ok", deps=["a", "b"]),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 1
        assert ready[0].id == "b"


class TestGetWorktreePath:
    """Test worktree path generation."""

    def test_default_worktree_path(self):
        """Default path uses worktree_base/task_id."""
        project = Project(name="test", worktree_base=".worktrees")
        spec = TaskSpec(
            version=1,
            status="ready_for_implementation",
            project=project,
            tasks=[Task(id="task-001", title="T", acceptance="ok")],
        )
        task = spec.tasks[0]
        path = get_worktree_path(Path("/project"), spec, task)
        assert path == Path("/project/.worktrees/task-001")

    def test_custom_worktree_path(self):
        """Custom worktree path overrides default."""
        project = Project(name="test")
        task = Task(id="task-001", title="T", acceptance="ok", worktree="custom/path")
        spec = TaskSpec(
            version=1,
            status="ready_for_implementation",
            project=project,
            tasks=[task],
        )
        path = get_worktree_path(Path("/project"), spec, task)
        assert path == Path("/project/custom/path")


class TestSubagentStopHelpers:
    """Test subagent_stop.py helper functions."""

    def test_is_worktree_file(self):
        """Worktree has .git as file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            git_file = path / ".git"
            git_file.write_text("gitdir: /main/repo/.git/worktrees/branch")
            assert is_worktree(path) is True

    def test_is_worktree_directory(self):
        """Main repo has .git as directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            git_dir = path / ".git"
            git_dir.mkdir()
            assert is_worktree(path) is False

    def test_is_worktree_missing(self):
        """No .git means not a worktree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            assert is_worktree(path) is False

    @patch("subagent_stop.run_git")
    def test_get_worktree_branch(self, mock_run):
        """Get branch name from worktree."""
        mock_run.return_value = (True, "feature-branch")
        branch = get_worktree_branch(Path("/some/path"))
        assert branch == "feature-branch"
        mock_run.assert_called_once()

    @patch("subagent_stop.run_git")
    def test_get_worktree_branch_detached(self, mock_run):
        """Detached HEAD returns None."""
        mock_run.return_value = (True, "HEAD")
        branch = get_worktree_branch(Path("/some/path"))
        assert branch is None

    @patch("subagent_stop.run_git")
    def test_get_main_branch_main(self, mock_run):
        """Detect main as default branch."""
        mock_run.return_value = (True, "abc123")
        branch = get_main_branch(Path("/repo"))
        assert branch == "main"

    @patch("subagent_stop.run_git")
    def test_get_main_branch_master(self, mock_run):
        """Fall back to master if main doesn't exist."""
        mock_run.return_value = (False, "")
        branch = get_main_branch(Path("/repo"))
        assert branch == "master"

    @patch("subagent_stop.run_git")
    def test_branch_in_linear_history_merged(self, mock_run):
        """Branch fully merged shows as in history."""
        # merge-base equals branch tip
        mock_run.side_effect = [
            (True, "abc123"),  # merge-base
            (True, "abc123"),  # branch tip
        ]
        result = is_branch_in_linear_history(Path("/repo"), "feature", "main")
        assert result is True

    @patch("subagent_stop.run_git")
    def test_branch_in_linear_history_rebased(self, mock_run):
        """Branch rebased (cherry-picked) shows as in history."""
        mock_run.side_effect = [
            (True, "abc123"),  # merge-base
            (True, "def456"),  # branch tip (different)
            (True, ""),  # cherry - no unpicked commits
        ]
        result = is_branch_in_linear_history(Path("/repo"), "feature", "main")
        assert result is True

    @patch("subagent_stop.run_git")
    def test_branch_not_in_history(self, mock_run):
        """Branch with unpicked commits not in history."""
        mock_run.side_effect = [
            (True, "abc123"),  # merge-base
            (True, "def456"),  # branch tip
            (True, "+ abc123 commit message"),  # cherry - has unpicked
        ]
        result = is_branch_in_linear_history(Path("/repo"), "feature", "main")
        assert result is False


class TestVerifyGate:
    """Test verify_gate.py functionality."""

    def test_run_verify_success(self):
        """Successful make verify returns True."""
        from verify_gate import run_verify

        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(".PHONY: verify\nverify:\n\t@echo 'OK'\n")
            success, output = run_verify(Path(tmpdir))
            assert success is True
            assert "OK" in output

    def test_run_verify_failure(self):
        """Failed make verify returns False."""
        from verify_gate import run_verify

        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(".PHONY: verify\nverify:\n\t@exit 1\n")
            success, output = run_verify(Path(tmpdir))
            assert success is False

    def test_run_verify_no_make(self):
        """Missing make returns False."""
        from verify_gate import run_verify

        with tempfile.TemporaryDirectory() as tmpdir:
            # No Makefile
            success, output = run_verify(Path(tmpdir))
            assert success is False
