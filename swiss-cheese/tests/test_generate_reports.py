"""Unit tests for swiss-cheese generate_reports script."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_reports import (
    VERSION,
    LAYERS,
    LayerResult,
    CoverageMetrics,
    TestRunMetrics,
    TraceabilityMetrics,
    ReportMeta,
    ValidationReport,
    get_git_hash,
    makefile_exists,
    has_target,
    run_make_target,
    run_layer_gates,
    collect_coverage,
    collect_test_results,
    collect_traceability,
    generate_report,
    write_report,
    dataclass_to_dict,
)


class TestLayerResult:
    """Test LayerResult dataclass."""

    def test_layer_result_fields(self):
        """LayerResult stores all fields."""
        result = LayerResult(
            status="PASS",
            checked_at="2026-02-03T12:00:00Z",
            message="All good",
            output="output text",
        )
        assert result.status == "PASS"
        assert result.checked_at == "2026-02-03T12:00:00Z"
        assert result.message == "All good"
        assert result.output == "output text"

    def test_layer_result_optional_fields(self):
        """LayerResult optional fields default to None."""
        result = LayerResult(status="PASS", checked_at="now")
        assert result.message is None
        assert result.output is None


class TestCoverageMetrics:
    """Test CoverageMetrics dataclass."""

    def test_coverage_defaults(self):
        """CoverageMetrics has sensible defaults."""
        metrics = CoverageMetrics()
        assert metrics.line_percent == 0.0
        assert metrics.branch_percent == 0.0
        assert metrics.threshold == 70
        assert metrics.meets_threshold is False

    def test_coverage_meets_threshold(self):
        """CoverageMetrics tracks threshold status."""
        metrics = CoverageMetrics(line_percent=75.0, threshold=70, meets_threshold=True)
        assert metrics.meets_threshold is True


class TestTestRunMetrics:
    """Test TestRunMetrics dataclass."""

    def test_test_run_metrics_defaults(self):
        """TestRunMetrics has sensible defaults."""
        metrics = TestRunMetrics()
        assert metrics.total == 0
        assert metrics.passed == 0
        assert metrics.failed == 0
        assert metrics.skipped == 0
        assert metrics.all_passed is False

    def test_test_run_metrics_all_passed(self):
        """TestRunMetrics tracks all_passed status."""
        metrics = TestRunMetrics(total=10, passed=10, failed=0, skipped=0, all_passed=True)
        assert metrics.all_passed is True


class TestGetGitHash:
    """Test get_git_hash function."""

    def test_returns_hash_in_git_repo(self):
        """Returns (full, short) hash in git repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)
            Path(tmpdir, "test.txt").write_text("test")
            subprocess.run(["git", "add", "test.txt"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "commit", "-m", "test"], cwd=tmpdir, capture_output=True)

            full_hash, short_hash = get_git_hash(Path(tmpdir))
            assert len(full_hash) == 40
            assert len(short_hash) == 7
            assert full_hash.startswith(short_hash)

    def test_returns_empty_in_non_git_dir(self):
        """Returns ("", "") for non-git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            full_hash, short_hash = get_git_hash(Path(tmpdir))
            assert full_hash == ""
            assert short_hash == ""


class TestMakefileExists:
    """Test makefile_exists function."""

    def test_makefile_exists(self):
        """Returns True when Makefile exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(".PHONY: test\ntest:\n\t@echo ok\n")
            assert makefile_exists(Path(tmpdir)) is True

    def test_makefile_missing(self):
        """Returns False when Makefile missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert makefile_exists(Path(tmpdir)) is False


class TestHasTarget:
    """Test has_target function."""

    def test_target_exists(self):
        """Returns True for existing target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(".PHONY: test\ntest:\n\t@echo ok\n")
            assert has_target(Path(tmpdir), "test") is True

    def test_target_missing(self):
        """Returns False for missing target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(".PHONY: test\ntest:\n\t@echo ok\n")
            assert has_target(Path(tmpdir), "nonexistent") is False


class TestRunMakeTarget:
    """Test run_make_target function."""

    def test_target_passes(self):
        """Returns (True, output) when target passes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(".PHONY: test\ntest:\n\t@echo 'Gate passed'\n")
            passed, output = run_make_target(Path(tmpdir), "test")
            assert passed is True
            assert "Gate passed" in output

    def test_target_fails(self):
        """Returns (False, output) when target fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(".PHONY: test\ntest:\n\t@echo 'Error' && exit 1\n")
            passed, output = run_make_target(Path(tmpdir), "test")
            assert passed is False
            assert "Error" in output

    def test_target_timeout(self):
        """Returns (False, message) on timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(".PHONY: slow\nslow:\n\t@sleep 10\n")
            passed, output = run_make_target(Path(tmpdir), "slow", timeout=1)
            assert passed is False
            assert "timed out" in output


class TestRunLayerGates:
    """Test run_layer_gates function."""

    def test_no_makefile_all_not_run(self):
        """All layers NOT_RUN when no Makefile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results = run_layer_gates(Path(tmpdir))
            for name in ["requirements", "tdd", "implementation", "verify"]:
                assert results[name].status == "NOT_RUN"
                assert "No Makefile" in results[name].message

    def test_missing_targets_not_run(self):
        """Missing targets marked as NOT_RUN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(".PHONY: validate-requirements\nvalidate-requirements:\n\t@echo ok\n")
            results = run_layer_gates(Path(tmpdir))
            assert results["requirements"].status == "PASS"
            assert results["tdd"].status == "NOT_RUN"
            assert "No target" in results["tdd"].message

    def test_passing_gates(self):
        """Passing gates marked as PASS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            targets = "\n".join(
                f".PHONY: {target}\n{target}:\n\t@echo ok"
                for _, target in LAYERS.values()
            )
            makefile.write_text(targets)
            results = run_layer_gates(Path(tmpdir))
            for name in ["requirements", "tdd", "implementation", "verify"]:
                assert results[name].status == "PASS"

    def test_failing_gate(self):
        """Failing gate marked as FAIL with output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text(
                ".PHONY: validate-requirements\n"
                "validate-requirements:\n\t@echo 'ERROR: missing file' && exit 1\n"
            )
            results = run_layer_gates(Path(tmpdir))
            assert results["requirements"].status == "FAIL"
            assert "missing file" in results["requirements"].output


class TestCollectCoverage:
    """Test collect_coverage function."""

    def test_no_coverage_file(self):
        """Returns None when no coverage file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = collect_coverage(Path(tmpdir))
            assert result is None

    def test_cargo_llvm_cov_format(self):
        """Parses cargo-llvm-cov JSON format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / "docs" / "plans"
            claude_dir.mkdir(parents=True)
            coverage_file = claude_dir / "coverage.json"
            coverage_file.write_text(json.dumps({
                "data": [{
                    "totals": {
                        "lines": {"percent": 75.5},
                        "branches": {"percent": 60.0},
                    }
                }]
            }))

            result = collect_coverage(Path(tmpdir))
            assert result is not None
            assert result.line_percent == 75.5
            assert result.branch_percent == 60.0
            assert result.meets_threshold is True  # 75.5 >= 70


class TestCollectTestResults:
    """Test collect_test_results function."""

    def test_no_test_file(self):
        """Returns None when no test results file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = collect_test_results(Path(tmpdir))
            assert result is None

    def test_cargo_test_json_format(self):
        """Parses cargo test --format=json output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / "docs" / "plans"
            claude_dir.mkdir(parents=True)
            test_file = claude_dir / "test-results.json"
            test_file.write_text("\n".join([
                '{"type": "test", "event": "ok", "name": "test1"}',
                '{"type": "test", "event": "ok", "name": "test2"}',
                '{"type": "test", "event": "failed", "name": "test3"}',
                '{"type": "test", "event": "ignored", "name": "test4"}',
            ]))

            result = collect_test_results(Path(tmpdir))
            assert result is not None
            assert result.total == 4
            assert result.passed == 2
            assert result.failed == 1
            assert result.skipped == 1
            assert result.all_passed is False


class TestCollectTraceability:
    """Test collect_traceability function."""

    def test_no_design_file(self):
        """Returns None when no design.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = collect_traceability(Path(tmpdir))
            assert result is None

    def test_parses_requirements(self):
        """Parses requirements from design.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            design_file = Path(tmpdir) / "design.toml"
            design_file.write_text("""
[[requirements]]
id = "REQ-001"
title = "First requirement"

[[requirements]]
id = "REQ-002"
title = "Second requirement"
""")

            result = collect_traceability(Path(tmpdir))
            assert result is not None
            assert result.requirements_count == 2


class TestGenerateReport:
    """Test generate_report function."""

    def test_git_hash_embedded(self):
        """Report includes current git hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)
            Path(tmpdir, "test.txt").write_text("test")
            subprocess.run(["git", "add", "test.txt"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "commit", "-m", "test"], cwd=tmpdir, capture_output=True)

            report = generate_report(Path(tmpdir))
            assert len(report.meta.git_hash) == 40
            assert len(report.meta.git_hash_short) == 7

    def test_timestamp_included(self):
        """Report includes timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = generate_report(Path(tmpdir))
            assert report.meta.timestamp != ""
            assert "T" in report.meta.timestamp  # ISO format

    def test_version_included(self):
        """Report includes generator version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = generate_report(Path(tmpdir))
            assert report.meta.generator_version == VERSION


class TestWriteReport:
    """Test write_report function."""

    def test_creates_report_directory(self):
        """Creates .swiss-cheese/reports/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = ValidationReport(
                meta=ReportMeta(
                    git_hash="abc1234",
                    git_hash_short="abc1234",
                    timestamp="2026-02-03T12:00:00Z",
                ),
                layers={"requirements": LayerResult(status="PASS", checked_at="now")},
            )
            report_path = write_report(report, Path(tmpdir))
            assert report_path.exists()
            assert report_path.parent.name == "reports"
            assert report_path.parent.parent.name == ".swiss-cheese"

    def test_writes_valid_json(self):
        """Writes valid JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = ValidationReport(
                meta=ReportMeta(
                    git_hash="abc1234",
                    git_hash_short="abc1234",
                    timestamp="2026-02-03T12:00:00Z",
                ),
                layers={"requirements": LayerResult(status="PASS", checked_at="now")},
            )
            report_path = write_report(report, Path(tmpdir))

            # Read and parse
            data = json.loads(report_path.read_text())
            assert data["meta"]["git_hash"] == "abc1234"
            assert data["layers"]["requirements"]["status"] == "PASS"


class TestDataclassToDict:
    """Test dataclass_to_dict helper."""

    def test_converts_simple_dataclass(self):
        """Converts simple dataclass to dict."""
        result = LayerResult(status="PASS", checked_at="now")
        d = dataclass_to_dict(result)
        assert isinstance(d, dict)
        assert d["status"] == "PASS"

    def test_converts_nested_dataclass(self):
        """Converts nested dataclasses."""
        report = ValidationReport(
            meta=ReportMeta(
                git_hash="abc",
                git_hash_short="abc",
                timestamp="now",
            ),
            layers={},
        )
        d = dataclass_to_dict(report)
        assert isinstance(d["meta"], dict)
        assert d["meta"]["git_hash"] == "abc"

    def test_handles_lists(self):
        """Handles lists in dataclass."""
        metrics = TraceabilityMetrics(
            requirements_count=2,
            requirements_with_tests=1,
            coverage_percent=50.0,
            unmapped_requirements=["REQ-001", "REQ-002"],
        )
        d = dataclass_to_dict(metrics)
        assert d["unmapped_requirements"] == ["REQ-001", "REQ-002"]
