"""Unit tests for schema.py - TOML design document validation.

These tests do not require any API keys and test the validation logic only.
"""
import sys
from pathlib import Path

# Add hooks directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from schema import (
    validate_design_document,
    get_schema_for_agent,
    ValidationResult,
    ValidationError,
    LAYERS,
    DESIGN_DOCUMENT_SCHEMA,
)


class TestDesignDocumentSchema:
    """Test the DESIGN_DOCUMENT_SCHEMA constant."""

    def test_schema_has_required_sections(self):
        """Verify schema defines all required sections."""
        assert "project" in DESIGN_DOCUMENT_SCHEMA
        assert "requirements" in DESIGN_DOCUMENT_SCHEMA
        assert "tasks" in DESIGN_DOCUMENT_SCHEMA

    def test_project_schema_fields(self):
        """Verify project section has expected fields."""
        project = DESIGN_DOCUMENT_SCHEMA["project"]
        assert project["_required"] is True
        assert "name" in project
        assert "version" in project
        assert project["name"]["required"] is True
        assert project["version"]["required"] is True

    def test_requirements_schema_is_array(self):
        """Verify requirements is marked as an array."""
        requirements = DESIGN_DOCUMENT_SCHEMA["requirements"]
        assert requirements["_is_array"] is True
        assert "_item_schema" in requirements

    def test_requirements_item_schema(self):
        """Verify requirement items have expected fields."""
        item_schema = DESIGN_DOCUMENT_SCHEMA["requirements"]["_item_schema"]
        assert "id" in item_schema
        assert "title" in item_schema
        assert "description" in item_schema
        assert "acceptance_criteria" in item_schema
        # Check pattern for ID
        assert item_schema["id"]["pattern"] == r"^REQ-\d+$"

    def test_tasks_schema_is_table(self):
        """Verify tasks is marked as a table."""
        tasks = DESIGN_DOCUMENT_SCHEMA["tasks"]
        assert tasks["_is_table"] is True
        assert "_item_schema" in tasks

    def test_tasks_valid_layers(self):
        """Verify tasks layer enum matches LAYERS constant."""
        task_layers = DESIGN_DOCUMENT_SCHEMA["tasks"]["_item_schema"]["layer"]["enum"]
        expected_layers = list(LAYERS.keys())
        assert set(task_layers) == set(expected_layers)


class TestLayers:
    """Test the LAYERS constant."""

    def test_layers_count(self):
        """Verify all 9 Swiss Cheese layers are defined."""
        assert len(LAYERS) == 9

    def test_layer_order(self):
        """Verify layers have sequential order values."""
        orders = [layer["order"] for layer in LAYERS.values()]
        assert sorted(orders) == list(range(1, 10))

    def test_layer_names(self):
        """Verify expected layer names exist."""
        expected = [
            "requirements",
            "architecture",
            "tdd",
            "implementation",
            "static_analysis",
            "formal_verification",
            "dynamic_analysis",
            "review",
            "safety",
        ]
        assert list(LAYERS.keys()) == expected

    def test_layers_have_makefile_targets(self):
        """Verify each layer has a makefile_target."""
        for name, layer in LAYERS.items():
            assert "makefile_target" in layer, f"Layer {name} missing makefile_target"
            assert layer["makefile_target"].startswith("validate-")

    def test_layer_dependencies(self):
        """Verify layer dependencies reference valid layers."""
        for name, layer in LAYERS.items():
            for dep in layer.get("depends_on", []):
                assert dep in LAYERS, f"Layer {name} has invalid dependency: {dep}"


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_valid_result_to_dict(self):
        """Test to_dict on valid result."""
        result = ValidationResult(valid=True, errors=[], warnings=[])
        d = result.to_dict()
        assert d["valid"] is True
        assert d["errors"] == []
        assert d["warnings"] == []

    def test_invalid_result_to_dict(self):
        """Test to_dict on invalid result with errors."""
        errors = [
            ValidationError(path="project.name", message="Missing required field"),
            ValidationError(path="tasks.foo", message="Invalid layer", value="bad"),
        ]
        result = ValidationResult(valid=False, errors=errors, warnings=["warn1"])
        d = result.to_dict()
        assert d["valid"] is False
        assert len(d["errors"]) == 2
        assert d["errors"][0]["path"] == "project.name"
        assert d["errors"][1]["value"] == "bad"
        assert d["warnings"] == ["warn1"]


class TestValidateDesignDocument:
    """Test validate_design_document function."""

    def test_empty_document_fails(self):
        """Empty document should fail validation."""
        result = validate_design_document({})
        assert result.valid is False
        assert len(result.errors) >= 3  # Missing project, requirements, tasks

    def test_missing_project_fails(self):
        """Document without project section should fail."""
        data = {
            "requirements": [],
            "tasks": {},
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "project" in paths

    def test_missing_project_name_fails(self):
        """Project without name should fail."""
        data = {
            "project": {"version": "1.0.0"},
            "requirements": [],
            "tasks": {},
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "project.name" in paths

    def test_missing_project_version_fails(self):
        """Project without version should fail."""
        data = {
            "project": {"name": "test"},
            "requirements": [],
            "tasks": {},
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "project.version" in paths

    def test_missing_requirements_fails(self):
        """Document without requirements should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "tasks": {},
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "requirements" in paths

    def test_requirements_not_array_fails(self):
        """Requirements as non-array should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": "not an array",
            "tasks": {},
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "requirements" in paths

    def test_requirement_missing_id_fails(self):
        """Requirement without id should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {"title": "Test", "description": "Desc", "acceptance_criteria": []}
            ],
            "tasks": {},
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "requirements[0].id" in paths

    def test_requirement_invalid_id_pattern_fails(self):
        """Requirement with invalid ID pattern should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "INVALID-001",
                    "title": "Test",
                    "description": "Desc",
                    "acceptance_criteria": [],
                }
            ],
            "tasks": {},
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "requirements[0].id" in paths

    def test_duplicate_requirement_id_fails(self):
        """Duplicate requirement IDs should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Test 1",
                    "description": "Desc",
                    "acceptance_criteria": [],
                },
                {
                    "id": "REQ-001",
                    "title": "Test 2",
                    "description": "Desc",
                    "acceptance_criteria": [],
                },
            ],
            "tasks": {},
        }
        result = validate_design_document(data)
        assert result.valid is False
        messages = [e.message for e in result.errors]
        assert any("Duplicate" in m for m in messages)

    def test_missing_tasks_fails(self):
        """Document without tasks should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Test",
                    "description": "Desc",
                    "acceptance_criteria": ["criterion"],
                }
            ],
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "tasks" in paths

    def test_task_missing_layer_fails(self):
        """Task without layer should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Test",
                    "description": "Desc",
                    "acceptance_criteria": ["criterion"],
                }
            ],
            "tasks": {
                "my_task": {"description": "Do something"},
            },
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "tasks.my_task.layer" in paths

    def test_task_invalid_layer_fails(self):
        """Task with invalid layer should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Test",
                    "description": "Desc",
                    "acceptance_criteria": ["criterion"],
                }
            ],
            "tasks": {
                "my_task": {"layer": "invalid_layer", "description": "Do something"},
            },
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "tasks.my_task.layer" in paths

    def test_task_missing_description_fails(self):
        """Task without description should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Test",
                    "description": "Desc",
                    "acceptance_criteria": ["criterion"],
                }
            ],
            "tasks": {
                "my_task": {"layer": "implementation"},
            },
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "tasks.my_task.description" in paths

    def test_task_invalid_dependency_fails(self):
        """Task with unknown dependency should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Test",
                    "description": "Desc",
                    "acceptance_criteria": ["criterion"],
                }
            ],
            "tasks": {
                "my_task": {
                    "layer": "implementation",
                    "description": "Do something",
                    "depends_on": ["nonexistent_task"],
                },
            },
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "tasks.my_task.depends_on" in paths

    def test_valid_minimal_document(self):
        """Minimal valid document should pass."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Test",
                    "description": "Desc",
                    "acceptance_criteria": ["criterion"],
                }
            ],
            "tasks": {
                "impl_task": {
                    "layer": "implementation",
                    "description": "Implement feature",
                },
            },
        }
        result = validate_design_document(data)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_valid_full_document(self):
        """Complete valid document should pass."""
        data = {
            "project": {
                "name": "test-project",
                "version": "1.0.0",
                "description": "A test project",
                "max_iterations": 3,
                "max_parallel_agents": 2,
            },
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "User Login",
                    "description": "Users should be able to log in",
                    "priority": "high",
                    "acceptance_criteria": ["Login form exists", "Validation works"],
                    "traces_to": ["REQ-002"],
                },
                {
                    "id": "REQ-002",
                    "title": "User Dashboard",
                    "description": "Users see dashboard after login",
                    "acceptance_criteria": ["Dashboard loads"],
                },
            ],
            "tasks": {
                "design_auth": {
                    "layer": "architecture",
                    "description": "Design authentication system",
                    "requirements": ["REQ-001"],
                },
                "impl_auth": {
                    "layer": "implementation",
                    "description": "Implement authentication",
                    "depends_on": ["design_auth"],
                    "requirements": ["REQ-001"],
                },
                "test_auth": {
                    "layer": "tdd",
                    "description": "Write auth tests",
                    "depends_on": ["design_auth"],
                    "requirements": ["REQ-001"],
                },
            },
            "gates": {
                "static_analysis": {
                    "target": "lint",
                    "fail_fast": True,
                },
            },
            "traceability": {
                "enabled": True,
                "report_formats": ["json"],
            },
        }
        result = validate_design_document(data)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_unknown_requirement_reference_warns(self):
        """Task referencing unknown requirement should produce warning."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Test",
                    "description": "Desc",
                    "acceptance_criteria": ["criterion"],
                }
            ],
            "tasks": {
                "my_task": {
                    "layer": "implementation",
                    "description": "Do something",
                    "requirements": ["REQ-999"],  # Does not exist
                },
            },
        }
        result = validate_design_document(data)
        # Should still be valid (warning, not error)
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("REQ-999" in w for w in result.warnings)

    def test_gate_missing_target_fails(self):
        """Gate without target should fail."""
        data = {
            "project": {"name": "test", "version": "1.0.0"},
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Test",
                    "description": "Desc",
                    "acceptance_criteria": ["criterion"],
                }
            ],
            "tasks": {
                "my_task": {"layer": "implementation", "description": "Do something"},
            },
            "gates": {
                "my_gate": {"fail_fast": True},  # Missing target
            },
        }
        result = validate_design_document(data)
        assert result.valid is False
        paths = [e.path for e in result.errors]
        assert "gates.my_gate.target" in paths


class TestGetSchemaForAgent:
    """Test get_schema_for_agent function."""

    def test_returns_string(self):
        """Should return a string."""
        schema = get_schema_for_agent()
        assert isinstance(schema, str)

    def test_contains_required_sections(self):
        """Schema should document required sections."""
        schema = get_schema_for_agent()
        assert "[project]" in schema
        assert "[[requirements]]" in schema
        assert "[tasks" in schema

    def test_contains_layer_list(self):
        """Schema should list all valid layers."""
        schema = get_schema_for_agent()
        for layer_name in LAYERS.keys():
            # Check that layer is mentioned (with or without underscore)
            layer_display = layer_name.replace("_", " ") if "_" in layer_name else layer_name
            assert layer_name in schema or layer_display in schema

    def test_contains_example_toml(self):
        """Schema should contain example TOML snippets."""
        schema = get_schema_for_agent()
        assert "```toml" in schema
        assert "name =" in schema
        assert "version =" in schema
