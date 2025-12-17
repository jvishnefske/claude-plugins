# Swiss Cheese hooks package
"""
Hook implementations for the Swiss Cheese verification model.

This package provides:
- schema: TOML design document schema and validation
- orchestrate: Parallel subagent orchestration with git worktrees
"""
from .schema import (
    validate_design_document,
    get_schema_for_agent,
    ValidationResult,
    ValidationError,
    LAYERS,
    DESIGN_DOCUMENT_SCHEMA,
)

__all__ = [
    "validate_design_document",
    "get_schema_for_agent",
    "ValidationResult",
    "ValidationError",
    "LAYERS",
    "DESIGN_DOCUMENT_SCHEMA",
]
