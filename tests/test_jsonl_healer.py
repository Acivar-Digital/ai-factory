import pytest
from pydantic import BaseModel

from factory.infra import output_sanitizer as osan
from factory.infra.jsonl_compiler import compile_jsonl_to_draft_plan_dict


class DummyEvidence(BaseModel):
    file_path: str
    content: str


class DummySubTask(BaseModel):
    id: str
    file_paths: list[str] = []
    evidence: list[DummyEvidence] = []


class DummyPlan(BaseModel):
    epic: dict = {}
    subtasks: list[DummySubTask] = []


def test_jsonl_compiler_basic():
    raw_jsonl = """
    {"epic": {"title": "Test Epic"}}
    {"subtasks": [{"id": "coder01", "file_paths": ["src2/a.py"]}]}
    """
    res = compile_jsonl_to_draft_plan_dict(raw_jsonl)
    assert res["epic"]["title"] == "Test Epic"
    assert len(res["subtasks"]) == 1
    assert res["subtasks"][0]["id"] == "coder01"
    # Auto-healing should add evidence item for src2/a.py
    assert len(res["subtasks"][0]["evidence"]) == 1
    assert res["subtasks"][0]["evidence"][0]["file_path"] == "src2/a.py"
    assert "[Auto-Healed]" in res["subtasks"][0]["evidence"][0]["content"]


def test_is_jsonl():
    assert osan.is_jsonl('{"a": 1}\n{"b": 2}') is True
    assert osan.is_jsonl('{"a": 1}') is False
    assert osan.is_jsonl('just text') is False


class SimpleModel(BaseModel):
    name: str
    value: int


def test_healer_mode_fallback(monkeypatch):
    # Mocking CONTROL_SHEET and Agent to test healer logic without actual LLM calls
    class FakeControlSheet:
        def model(self, key):
            if key == "healer_mode":
                return "fake_healer_model"
            return None

    monkeypatch.setattr("factory.infra.control.CONTROL_SHEET", FakeControlSheet())

    class FakeResult:
        def __init__(self):
            self.output = SimpleModel(name="healed_name", value=42)

    class FakeAgent:
        def __init__(self, model, output_type, **kwargs):
            self.output_type = output_type

        def run_sync(self, prompt):
            return FakeResult()

    monkeypatch.setattr("pydantic_ai.Agent", FakeAgent)

    # Malformed raw input (missing value field)
    malformed = '{"name": "test"}'
    
    # Passing malformed input should trigger Healer and return SimpleModel instance successfully
    result = osan.clean_role_output(malformed, SimpleModel)
    assert result.name == "healed_name"
    assert result.value == 42


def test_self_learning_loop(monkeypatch):
    # Reset/clear FROZEN_KEY_ALIASES at the beginning of the test
    original_aliases = osan.FROZEN_KEY_ALIASES.copy()
    osan.FROZEN_KEY_ALIASES.clear()

    try:
        # 1. Deformed JSON input (has 'value_alias' instead of 'value')
        deformed_json = '{"name": "test", "value_alias": 100}'

        # The normalizer with empty FROZEN_KEY_ALIASES will not translate the key,
        # so SimpleModel validation should fail (value is required)
        with pytest.raises(Exception):
            SimpleModel.model_validate_json(osan.normalize_role_output(deformed_json))

        # 2. Trigger healer mode using mocked healer returning valid SimpleModel
        class FakeControlSheet:
            def model(self, key):
                if key == "healer_mode":
                    return "fake_healer_model"
                return None

        monkeypatch.setattr("factory.infra.control.CONTROL_SHEET", FakeControlSheet())

        class FakeResult:
            def __init__(self):
                self.output = SimpleModel(name="test", value=100)

        class FakeAgent:
            def __init__(self, model, output_type, **kwargs):
                self.output_type = output_type

            def run_sync(self, prompt):
                return FakeResult()

        monkeypatch.setattr("pydantic_ai.Agent", FakeAgent)

        # Capturing suggestion telemetry prints
        captured_suggestions = []
        def mock_detect_and_log_aliases(input_dict, output_dict):
            # Record suggestion
            for k in input_dict:
                if k == "value_alias":
                    captured_suggestions.append((k, "value"))
            osan._detect_and_log_aliases(input_dict, output_dict)

        monkeypatch.setattr(osan, "_detect_and_log_aliases", mock_detect_and_log_aliases)

        # Call clean_role_output, which fails validation first, calls healer, and triggers telemetry
        res = osan.clean_role_output(deformed_json, SimpleModel)
        assert res.value == 100
        assert len(captured_suggestions) > 0

        # 3. Add the new exception/alias to FROZEN_KEY_ALIASES (simulating developer adding it)
        osan.FROZEN_KEY_ALIASES["value_alias"] = "value"

        # 4. Now, the normalizer should translate 'value_alias' to 'value', so it parses directly without healing
        normalized = osan.normalize_role_output(deformed_json)
        parsed_directly = SimpleModel.model_validate_json(normalized)
        assert parsed_directly.value == 100

    finally:
        # Reset FROZEN_KEY_ALIASES back to its original state
        osan.FROZEN_KEY_ALIASES.clear()
        osan.FROZEN_KEY_ALIASES.update(original_aliases)


def test_registry_str_mapping():
    from factory.common.registry import OUTPUT_TYPE_REGISTRY
    assert "str" in OUTPUT_TYPE_REGISTRY
    assert OUTPUT_TYPE_REGISTRY["str"] is str


def test_generic_jsonl_compiler():
    from factory.infra.jsonl_compiler import compile_jsonl_to_dict
    raw_jsonl = '{"a": 1}\n{"b": 2}\n{"nested": {"x": "y"}}'
    compiled = compile_jsonl_to_dict(raw_jsonl)
    assert compiled["a"] == 1
    assert compiled["b"] == 2
    assert compiled["nested"]["x"] == "y"

