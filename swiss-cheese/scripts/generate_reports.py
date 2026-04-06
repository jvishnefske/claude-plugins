#!/usr/bin/env python3
"""
Swiss Cheese Report Generator.

Runs all 4 layer Makefile targets, collects metrics, and writes
.swiss-cheese/reports/validation_report.json.

Usage:
    python3 generate_reports.py [--project-dir PATH]

Exit codes:
    0: All validations passed
    1: One or more validations failed
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

VERSION = "1.0.0"

# Layer definitions: layer_num -> (name, make_target)
LAYERS: dict[int, Tuple[str, str]] = {
    1: ("requirements", "validate-requirements"),
    2: ("tdd", "validate-tdd"),
    3: ("implementation", "validate-implementation"),
    4: ("verify", "validate-verify"),
}

REPORT_DIR = Path(".swiss-cheese/reports")
REPORT_FILE = "validation_report.json"


@dataclass
class LayerResult:
    """Result of running a single layer gate."""
    status: str  # "PASS", "FAIL", "NOT_RUN"
    checked_at: str
    message: Optional[str] = None
    output: Optional[str] = None


@dataclass
class CoverageMetrics:
    """Code coverage metrics."""
    line_percent: float = 0.0
    branch_percent: float = 0.0
    threshold: int = 70
    meets_threshold: bool = False


@dataclass
class TestRunMetrics:
    """Test run metrics."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    all_passed: bool = False


@dataclass
class TraceabilityMetrics:
    """Requirements traceability metrics."""
    requirements_count: int = 0
    requirements_with_tests: int = 0
    coverage_percent: float = 0.0
    unmapped_requirements: list[str] = field(default_factory=list)


@dataclass
class ReportMeta:
    """Report metadata."""
    git_hash: str
    git_hash_short: str
    timestamp: str
    generator_version: str = VERSION


@dataclass
class ValidationReport:
    """Complete validation report."""
    meta: ReportMeta
    layers: dict[str, LayerResult]
    coverage: Optional[CoverageMetrics] = None
    tests: Optional[TestRunMetrics] = None
    traceability: Optional[TraceabilityMetrics] = None


def get_git_hash(project_dir: Path) -> Tuple[str, str]:
    """Get current git hash (full and short).

    Returns ("", "") if not a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            full_hash = result.stdout.strip()
            return full_hash, full_hash[:7]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "", ""


def makefile_exists(project_dir: Path) -> bool:
    """Check if Makefile exists."""
    return (project_dir / "Makefile").exists()


def has_target(project_dir: Path, target: str) -> bool:
    """Check if Makefile has a specific target."""
    try:
        result = subprocess.run(
            ["make", "-n", target],
            cwd=project_dir,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def run_make_target(
    project_dir: Path,
    target: str,
    timeout: int = 120
) -> Tuple[bool, str]:
    """Run a Makefile target.

    Returns (passed, output).
    """
    try:
        result = subprocess.run(
            ["make", target],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr)[-2000:]  # Keep last 2KB
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"Target '{target}' timed out after {timeout}s"
    except FileNotFoundError:
        return False, "make not found"
    except OSError as e:
        return False, str(e)


def run_layer_gates(project_dir: Path) -> dict[str, LayerResult]:
    """Run all layer gates and collect results."""
    results = {}
    now = datetime.now(timezone.utc).isoformat()

    if not makefile_exists(project_dir):
        # No Makefile - mark all as NOT_RUN
        for layer_num, (name, _) in LAYERS.items():
            results[name] = LayerResult(
                status="NOT_RUN",
                checked_at=now,
                message="No Makefile found",
            )
        return results

    for layer_num in sorted(LAYERS.keys()):
        name, target = LAYERS[layer_num]

        if not has_target(project_dir, target):
            results[name] = LayerResult(
                status="NOT_RUN",
                checked_at=now,
                message=f"No target: {target}",
            )
            continue

        passed, output = run_make_target(project_dir, target)
        results[name] = LayerResult(
            status="PASS" if passed else "FAIL",
            checked_at=now,
            output=output if not passed else None,
        )

    return results


def collect_coverage(project_dir: Path) -> Optional[CoverageMetrics]:
    """Collect coverage metrics from coverage.json or cargo llvm-cov."""
    # Try reading existing coverage.json
    coverage_file = project_dir / "docs" / "plans" / "coverage.json"
    if coverage_file.exists():
        try:
            data = json.loads(coverage_file.read_text())
            # Handle cargo-llvm-cov format
            if "data" in data:
                totals = data["data"][0].get("totals", {})
                lines = totals.get("lines", {})
                branches = totals.get("branches", {})
                line_pct = lines.get("percent", 0.0)
                branch_pct = branches.get("percent", 0.0)
            else:
                # Simple format
                line_pct = data.get("line_percent", 0.0)
                branch_pct = data.get("branch_percent", 0.0)

            threshold = 70
            return CoverageMetrics(
                line_percent=round(line_pct, 1),
                branch_percent=round(branch_pct, 1),
                threshold=threshold,
                meets_threshold=line_pct >= threshold,
            )
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    return None


def collect_test_results(project_dir: Path) -> Optional[TestRunMetrics]:
    """Collect test results from test-results.json or cargo test --format=json."""
    test_file = project_dir / "docs" / "plans" / "test-results.json"
    if test_file.exists():
        try:
            lines = test_file.read_text().strip().split('\n')
            passed = failed = skipped = 0

            for line in lines:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "test":
                        if event.get("event") == "ok":
                            passed += 1
                        elif event.get("event") == "failed":
                            failed += 1
                        elif event.get("event") == "ignored":
                            skipped += 1
                except json.JSONDecodeError:
                    continue

            total = passed + failed + skipped
            if total > 0:
                return TestRunMetrics(
                    total=total,
                    passed=passed,
                    failed=failed,
                    skipped=skipped,
                    all_passed=(failed == 0),
                )
        except OSError:
            pass

    return None


def collect_traceability(project_dir: Path) -> Optional[TraceabilityMetrics]:
    """Build traceability matrix from design.toml and test patterns."""
    design_file = project_dir / "design.toml"
    if not design_file.exists():
        return None

    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return None

    try:
        data = tomllib.loads(design_file.read_text())
        requirements = data.get("requirements", [])
        req_ids = [r.get("id") for r in requirements if r.get("id")]

        if not req_ids:
            return None

        # Find tests that match test_req_NNN pattern
        test_pattern = re.compile(r'test_req_(\d+)', re.IGNORECASE)
        mapped_reqs = set()

        # Search test files for requirement mappings
        for test_file in project_dir.rglob("**/test*.rs"):
            try:
                content = test_file.read_text()
                for match in test_pattern.finditer(content):
                    req_num = match.group(1)
                    # Try different formats: REQ-001, REQ-1, etc.
                    mapped_reqs.add(f"REQ-{req_num.zfill(3)}")
                    mapped_reqs.add(f"REQ-{req_num}")
            except OSError:
                continue

        # Also check Python test files
        for test_file in project_dir.rglob("**/test*.py"):
            try:
                content = test_file.read_text()
                for match in test_pattern.finditer(content):
                    req_num = match.group(1)
                    mapped_reqs.add(f"REQ-{req_num.zfill(3)}")
                    mapped_reqs.add(f"REQ-{req_num}")
            except OSError:
                continue

        # Calculate coverage
        covered = len([r for r in req_ids if r in mapped_reqs])
        total = len(req_ids)
        unmapped = [r for r in req_ids if r not in mapped_reqs]

        return TraceabilityMetrics(
            requirements_count=total,
            requirements_with_tests=covered,
            coverage_percent=round((covered / total * 100) if total > 0 else 0.0, 1),
            unmapped_requirements=unmapped,
        )
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def generate_report(project_dir: Path) -> ValidationReport:
    """Generate complete validation report."""
    git_hash, git_hash_short = get_git_hash(project_dir)
    timestamp = datetime.now(timezone.utc).isoformat()

    meta = ReportMeta(
        git_hash=git_hash,
        git_hash_short=git_hash_short,
        timestamp=timestamp,
    )

    layers = run_layer_gates(project_dir)
    coverage = collect_coverage(project_dir)
    tests = collect_test_results(project_dir)
    traceability = collect_traceability(project_dir)

    return ValidationReport(
        meta=meta,
        layers=layers,
        coverage=coverage,
        tests=tests,
        traceability=traceability,
    )


def dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses to dicts."""
    if hasattr(obj, '__dataclass_fields__'):
        return {k: dataclass_to_dict(v) for k, v in asdict(obj).items()}
    elif isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [dataclass_to_dict(v) for v in obj]
    return obj


def write_report(report: ValidationReport, project_dir: Path) -> Path:
    """Write report to JSON file."""
    report_dir = project_dir / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = report_dir / REPORT_FILE
    report_dict = dataclass_to_dict(report)

    # Remove None values for cleaner JSON
    def remove_none(d: dict) -> dict:
        return {k: remove_none(v) if isinstance(v, dict) else v
                for k, v in d.items() if v is not None}

    report_dict = remove_none(report_dict)
    report_path.write_text(json.dumps(report_dict, indent=2) + "\n")

    return report_path


def print_summary(report: ValidationReport) -> None:
    """Print human-readable summary."""
    print("=" * 60)
    print("Swiss Cheese Validation Report")
    print("=" * 60)
    print(f"Git Hash: {report.meta.git_hash_short}")
    print(f"Timestamp: {report.meta.timestamp}")
    print()

    print("Layer Results:")
    all_pass = True
    for layer_num in sorted(LAYERS.keys()):
        name, _ = LAYERS[layer_num]
        result = report.layers.get(name)
        if result:
            status_icon = {
                "PASS": "[PASS]",
                "FAIL": "[FAIL]",
                "NOT_RUN": "[SKIP]",
            }.get(result.status, "[????]")
            print(f"  {layer_num}. {name:20} {status_icon}")
            if result.status == "FAIL":
                all_pass = False
    print()

    if report.coverage:
        print(f"Coverage: {report.coverage.line_percent}% lines "
              f"(threshold: {report.coverage.threshold}%)")

    if report.tests:
        print(f"Tests: {report.tests.passed}/{report.tests.total} passed")

    if report.traceability:
        print(f"Traceability: {report.traceability.requirements_with_tests}/"
              f"{report.traceability.requirements_count} requirements covered")

    print("=" * 60)

    if all_pass:
        print("Result: ALL GATES PASSED")
    else:
        print("Result: VALIDATION FAILED")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Swiss Cheese validation report"
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())),
        help="Project directory (default: CLAUDE_PROJECT_DIR or cwd)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress summary output",
    )

    args = parser.parse_args()
    project_dir = args.project_dir.resolve()

    if not project_dir.exists():
        print(f"Error: Project directory not found: {project_dir}", file=sys.stderr)
        return 1

    report = generate_report(project_dir)
    report_path = write_report(report, project_dir)

    if not args.quiet:
        print_summary(report)
        print(f"\nReport written to: {report_path}")

    # Exit code based on layer results
    for result in report.layers.values():
        if result.status == "FAIL":
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
