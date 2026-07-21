#!/usr/bin/env python3
"""
Strict JSON Schema Validation Layer for MCP Tool Calls.

Validates incoming tool arguments against each tool's declared parameter schema
before the tool function executes. Enforces:
  - additionalProperties: false  (no extra/renamed fields)
  - Required fields must be present
  - Type coercion for ints/floats/strings
  - relative_path fields reject absolute paths

Designed as a decorator (@validate_args) applied to @mcp.tool() functions.
"""

from __future__ import annotations

import inspect
import functools
from typing import (
    Annotated, Any, Callable, Dict, List, Optional, Tuple, Union, get_type_hints,
    get_origin, get_args
)

# ---------------------------------------------------------------------------
# Schema registry — populated by @validate_args
# ---------------------------------------------------------------------------
_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {}


def get_tool_schemas() -> Dict[str, Dict[str, Any]]:
    """Return the full registry of tool_name -> JSON schema."""
    return dict(_TOOL_SCHEMAS)


# ---------------------------------------------------------------------------
# Type -> JSON Schema type mapping
# ---------------------------------------------------------------------------
def _python_type_to_schema(tp: Any) -> Dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema fragment."""
    origin = get_origin(tp)
    args = get_args(tp)

    # Handle Annotated[T, metadata]
    if origin is Annotated:
        base_type = args[0]
        schema = _python_type_to_schema(base_type)
        # Add description if present in metadata
        if len(args) > 1 and isinstance(args[1], str):
            schema["description"] = args[1]
        return schema

    # Optional[X] == Union[X, None]
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _python_type_to_schema(non_none[0])
        return {"anyOf": [_python_type_to_schema(a) for a in non_none]}

    if origin is list or origin is List:
        item_schema = _python_type_to_schema(args[0]) if args else {}
        return {"type": "array", "items": item_schema}

    if origin is dict or origin is Dict:
        return {"type": "object"}

    # Primitives
    if tp is str:
        return {"type": "string"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is bool:
        return {"type": "boolean"}

    return {}  # unknown


def _is_optional(tp: Any) -> bool:
    """Check if a type annotation is Optional[X]."""
    origin = get_origin(tp)
    if origin is Union:
        return type(None) in get_args(tp)
    return False


# ---------------------------------------------------------------------------
# Schema builder
# ---------------------------------------------------------------------------
def build_tool_schema(func: Callable) -> Dict[str, Any]:
    """
    Build a JSON Schema (draft-07 style) from a function's signature.

    Returns a dict with:
      - properties: {name: {type, ...}}
      - required: [names]
      - additionalProperties: false
    """
    sig = inspect.signature(func)
    hints = get_type_hints(func, include_extras=True)

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        tp = hints.get(name, str)
        prop = _python_type_to_schema(tp)

        if param.default is inspect.Parameter.empty and not _is_optional(tp):
            required.append(name)

        if param.default is not inspect.Parameter.empty and param.default is not None:
            prop["default"] = param.default

        properties[name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
class ValidationError:
    """Structured validation error."""
    MISSING_REQUIRED = "MISSING_REQUIRED"
    EXTRA_FIELD = "EXTRA_FIELD"
    TYPE_ERROR = "TYPE_ERROR"
    PATH_VIOLATION = "PATH_VIOLATION"

    def __init__(self, code: str, field: str, message: str,
                 expected: str = "", actual: str = ""):
        self.code = code
        self.field = field
        self.message = message
        self.expected = expected
        self.actual = actual

    def to_dict(self) -> Dict[str, Any]:
        d = {"code": self.code, "field": self.field, "message": self.message}
        if self.expected:
            d["expected"] = self.expected
        if self.actual:
            d["actual"] = self.actual
        return d


def _coerce_value(value: Any, schema: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
    """
    Attempt to coerce a value to the expected type.
    Returns (coered_value, error_message).
    """
    expected_type = schema.get("type", "")
    if not expected_type:
        return value, None

    if expected_type == "string":
        if isinstance(value, str):
            return value, None
        return str(value), None  # coerce to string

    if expected_type == "integer":
        if isinstance(value, int) and not isinstance(value, bool):
            return value, None
        if isinstance(value, float) and value == int(value):
            return int(value), None
        if isinstance(value, str):
            try:
                return int(value), None
            except ValueError:
                return value, f"Cannot coerce '{value}' to integer"
        return value, f"Expected integer, got {type(value).__name__}"

    if expected_type == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value), None
        if isinstance(value, str):
            try:
                return float(value), None
            except ValueError:
                return value, f"Cannot coerce '{value}' to number"
        return value, f"Expected number, got {type(value).__name__}"

    if expected_type == "boolean":
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str):
            if value.lower() in ("true", "1", "yes"):
                return True, None
            if value.lower() in ("false", "0", "no"):
                return False, None
        if isinstance(value, (int, float)):
            return bool(value), None
        return value, f"Expected boolean, got {type(value).__name__}"

    if expected_type == "array":
        if isinstance(value, list):
            return value, None
        if isinstance(value, str):
            # Try JSON parse
            try:
                import json
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed, None
            except Exception:
                pass
        return value, f"Expected array, got {type(value).__name__}"

    return value, None


def _is_absolute_path(value: str) -> bool:
    """Check if a string looks like an absolute path."""
    if not isinstance(value, str):
        return False
    # Unix absolute
    if value.startswith("/"):
        return True
    # Windows absolute
    if len(value) >= 2 and value[1] == ":":
        return True
    # UNC path
    if value.startswith("\\\\"):
        return True
    return False


def _normalize_workspace_path(value: str) -> str:
    """If value is an absolute path within the workspace root, convert it to relative."""
    if not isinstance(value, str) or not _is_absolute_path(value):
        return value

    from pathlib import Path
    try:
        path_obj = Path(value).resolve()
        file_path = Path(__file__).resolve()
        for parent in [file_path.parents[2], file_path.parents[3], Path.cwd()]:
            try:
                rel = path_obj.relative_to(parent)
                if not str(rel).startswith(".."):
                    return rel.as_posix()
            except ValueError:
                continue
    except Exception:
        pass
    return value


def validate_against_schema(
    tool_name: str,
    args: Dict[str, Any],
    schema: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[ValidationError]]:
    """
    Validate incoming tool arguments against the schema.

    Returns (cleaned_args, errors).
    cleaned_args has extra fields removed and types coerced.
    errors is a list of ValidationError objects.
    """
    errors: List[ValidationError] = []
    cleaned: Dict[str, Any] = {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    # Check for missing required fields
    for field_name in required:
        if field_name not in args:
            errors.append(ValidationError(
                code=ValidationError.MISSING_REQUIRED,
                field=field_name,
                message=f"Missing required field: '{field_name}'. "
                        f"Tool '{tool_name}' requires: {', '.join(required)}",
            ))

    # Check for extra fields (additionalProperties: false)
    for field_name in args:
        if field_name not in properties:
            errors.append(ValidationError(
                code=ValidationError.EXTRA_FIELD,
                field=field_name,
                message=f"Unexpected field: '{field_name}'. "
                        f"Allowed fields for '{tool_name}': {', '.join(sorted(properties))}",
            ))

    # Validate and coerce present fields
    for field_name, value in args.items():
        if field_name not in properties:
            continue  # already reported as extra

        prop_schema = properties[field_name]
        coerced, err = _coerce_value(value, prop_schema)
        if err:
            errors.append(ValidationError(
                code=ValidationError.TYPE_ERROR,
                field=field_name,
                message=f"Type error on '{field_name}': {err}",
                expected=prop_schema.get("type", "any"),
                actual=type(value).__name__,
            ))
        else:
            cleaned[field_name] = coerced

        # Path validation: fields named "relative_path" must not be absolute
        if field_name == "relative_path" and isinstance(coerced, str):
            coerced = _normalize_workspace_path(coerced)
            cleaned[field_name] = coerced
            if _is_absolute_path(coerced):
                errors.append(ValidationError(
                    code=ValidationError.PATH_VIOLATION,
                    field=field_name,
                    message=f"'{field_name}' must be a relative path, not absolute: '{coerced}'. "
                            f"Use repository-relative paths only (e.g. 'src/engine/bazi_data.py')",
                ))

    return cleaned, errors


# ---------------------------------------------------------------------------
# Error formatter — produces LLM-readable feedback
# ---------------------------------------------------------------------------
def format_validation_errors(tool_name: str, errors: List[ValidationError]) -> Dict[str, Any]:
    """Format validation errors into a structured response for the LLM."""
    return {
        "success": False,
        "message": f"Tool call '{tool_name}' failed validation with {len(errors)} error(s).",
        "validation_errors": [e.to_dict() for e in errors],
        "hint": (
            "Fix the arguments and retry. "
            "Use ONLY the declared field names. "
            "Do not add extra fields. "
            "All file paths must be relative."
        ),
    }


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------
def validate_args(func: Callable) -> Callable:
    """
    Decorator that validates tool arguments against the function's schema
    before calling the function.

    On validation failure, returns a structured error dict instead of calling
    the tool. On success, calls the tool with cleaned (coerced) arguments.

    Registers the tool's schema in _TOOL_SCHEMAS.
    """
    tool_name = func.__name__
    schema = build_tool_schema(func)
    _TOOL_SCHEMAS[tool_name] = schema

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # FastMCP passes arguments as keyword arguments
        # But some tools may receive a single dict arg
        if args and len(args) == 1 and isinstance(args[0], dict) and not kwargs:
            incoming = args[0]
        else:
            incoming = kwargs

        cleaned, errors = validate_against_schema(tool_name, incoming, schema)
        if errors:
            return format_validation_errors(tool_name, errors)

        # Call the original function with cleaned args
        if args and len(args) == 1 and isinstance(args[0], dict) and not kwargs:
            return func(**cleaned)
        return func(**cleaned)

    # Attach schema for introspection
    wrapper._tool_schema = schema  # type: ignore[attr-defined]
    wrapper._tool_name = tool_name  # type: ignore[attr-defined]
    return wrapper
