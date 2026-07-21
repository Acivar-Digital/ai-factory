#!/usr/bin/env python3
"""
Unit tests for the MCP tool argument validation layer.

Tests cover:
  - Missing required fields
  - Extra/unknown fields (additionalProperties: false)
  - Type errors and coercion
  - Optional fields with defaults
  - Absolute path rejection in relative_path fields
  - Valid calls pass through cleanly
"""

import sys
import os
import unittest
from typing import Any, Dict, Optional

# Add the infra/codebase directory to the path so we can import validator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validator import (
    build_tool_schema,
    validate_against_schema,
    format_validation_errors,
    ValidationError,
    _is_absolute_path,
)


# ---------------------------------------------------------------------------
# Helper: sample tool functions to build schemas from
# ---------------------------------------------------------------------------
def sample_read_file(relative_path: str, start_line: int = 1, end_line: Optional[int] = None) -> Dict[str, Any]:
    """Simulates read_file tool signature."""
    pass


def sample_search_codebase(query: str, collection: str, limit: int = 10, min_score: float = 0.0) -> Dict[str, Any]:
    """Simulates search_codebase tool signature."""
    pass


def sample_remember_fact(key: str, value: str) -> str:
    """Simulates remember_fact tool signature."""
    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestBuildToolSchema(unittest.TestCase):
    """Test schema generation from function signatures."""

    def test_required_fields(self):
        schema = build_tool_schema(sample_read_file)
        self.assertIn("relative_path", schema["required"])
        self.assertNotIn("start_line", schema["required"])
        self.assertNotIn("end_line", schema["required"])

    def test_optional_fields(self):
        schema = build_tool_schema(sample_read_file)
        self.assertIn("start_line", schema["properties"])
        self.assertIn("end_line", schema["properties"])

    def test_additional_properties_false(self):
        schema = build_tool_schema(sample_read_file)
        self.assertFalse(schema["additionalProperties"])

    def test_type_mapping(self):
        schema = build_tool_schema(sample_read_file)
        self.assertEqual(schema["properties"]["relative_path"], {"type": "string"})
        self.assertEqual(schema["properties"]["start_line"], {"type": "integer", "default": 1})

    def test_all_required_for_no_defaults(self):
        schema = build_tool_schema(sample_remember_fact)
        self.assertEqual(set(schema["required"]), {"key", "value"})


class TestValidateAgainstSchema(unittest.TestCase):
    """Test argument validation logic."""

    def setUp(self):
        self.schema = build_tool_schema(sample_read_file)

    # --- Missing required ---
    def test_missing_required_field(self):
        args = {"start_line": 5}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertTrue(any(e.code == ValidationError.MISSING_REQUIRED for e in errors))
        error_fields = [e.field for e in errors]
        self.assertIn("relative_path", error_fields)

    # --- Extra fields ---
    def test_extra_field(self):
        args = {"relative_path": "src/main.py", "AbsolutePath": "/home/user/main.py"}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertTrue(any(e.code == ValidationError.EXTRA_FIELD for e in errors))
        error_fields = [e.field for e in errors]
        self.assertIn("AbsolutePath", error_fields)

    def test_multiple_extra_fields(self):
        args = {"relative_path": "src/main.py", "AbsolutePath": "/x", "EndLine": 50}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        extra_errors = [e for e in errors if e.code == ValidationError.EXTRA_FIELD]
        self.assertEqual(len(extra_errors), 2)

    # --- Type coercion ---
    def test_valid_types_pass(self):
        args = {"relative_path": "src/main.py", "start_line": 10}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertEqual(len(errors), 0)
        self.assertEqual(cleaned["relative_path"], "src/main.py")
        self.assertEqual(cleaned["start_line"], 10)

    def test_int_coercion_from_float(self):
        args = {"relative_path": "src/main.py", "start_line": 10.0}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertEqual(len(errors), 0)
        self.assertEqual(cleaned["start_line"], 10)

    def test_type_error_on_bad_int(self):
        args = {"relative_path": "src/main.py", "start_line": "abc"}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertTrue(any(e.code == ValidationError.TYPE_ERROR for e in errors))

    # --- Path validation ---
    def test_absolute_path_rejected(self):
        args = {"relative_path": "/home/user/main.py"}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertTrue(any(e.code == ValidationError.PATH_VIOLATION for e in errors))

    def test_relative_path_accepted(self):
        args = {"relative_path": "src/engine/bazi_data.py"}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertEqual(len(errors), 0)

    def test_windows_absolute_path_rejected(self):
        args = {"relative_path": "C:\\Users\\file.py"}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertTrue(any(e.code == ValidationError.PATH_VIOLATION for e in errors))

    # --- Valid call ---
    def test_fully_valid_call(self):
        args = {"relative_path": "src/main.py", "start_line": 1, "end_line": 100}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertEqual(len(errors), 0)
        self.assertEqual(cleaned, {"relative_path": "src/main.py", "start_line": 1, "end_line": 100})

    def test_minimal_valid_call(self):
        args = {"relative_path": "README.md"}
        cleaned, errors = validate_against_schema("read_file", args, self.schema)
        self.assertEqual(len(errors), 0)
        self.assertEqual(cleaned, {"relative_path": "README.md"})


class TestFormatValidationErrors(unittest.TestCase):
    """Test error formatting for LLM consumption."""

    def test_format_has_success_false(self):
        schema = build_tool_schema(sample_read_file)
        _, errors = validate_against_schema("read_file", {"AbsolutePath": "/x"}, schema)
        result = format_validation_errors("read_file", errors)
        self.assertFalse(result["success"])
        self.assertIn("validation_errors", result)
        self.assertIn("hint", result)

    def test_format_includes_error_codes(self):
        schema = build_tool_schema(sample_read_file)
        _, errors = validate_against_schema("read_file", {"AbsolutePath": "/x"}, schema)
        result = format_validation_errors("read_file", errors)
        codes = [e["code"] for e in result["validation_errors"]]
        self.assertIn("EXTRA_FIELD", codes)


class TestIsAbsolutePath(unittest.TestCase):
    """Test absolute path detection."""

    def test_unix_absolute(self):
        self.assertTrue(_is_absolute_path("/home/user/file.py"))

    def test_windows_absolute(self):
        self.assertTrue(_is_absolute_path("C:\\Users\\file.py"))

    def test_unc_path(self):
        self.assertTrue(_is_absolute_path("\\\\server\\share\\file.py"))

    def test_relative_path(self):
        self.assertFalse(_is_absolute_path("src/main.py"))

    def test_dot_relative(self):
        self.assertFalse(_is_absolute_path("./src/main.py"))

    def test_non_string(self):
        self.assertFalse(_is_absolute_path(123))


class TestSearchCodebaseSchema(unittest.TestCase):
    """Test with search_codebase-like signature."""

    def setUp(self):
        self.schema = build_tool_schema(sample_search_codebase)

    def test_valid_search(self):
        args = {"query": "财星", "collection": "baziforecaster"}
        cleaned, errors = validate_against_schema("search_codebase", args, self.schema)
        self.assertEqual(len(errors), 0)

    def test_missing_query(self):
        args = {"collection": "baziforecaster"}
        cleaned, errors = validate_against_schema("search_codebase", args, self.schema)
        self.assertTrue(any(e.code == ValidationError.MISSING_REQUIRED and e.field == "query" for e in errors))

    def test_extra_field_in_search(self):
        args = {"query": "财星", "collection": "baziforecaster", "min_score": 0.5, "extra_field": True}
        cleaned, errors = validate_against_schema("search_codebase", args, self.schema)
        self.assertTrue(any(e.code == ValidationError.EXTRA_FIELD and e.field == "extra_field" for e in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
