"""Coder agent — execution and editing."""
from pathlib import Path
import yaml
from factory.infra.tools import SkillSpec

def build_coder_spec() -> SkillSpec:
    """Build the coder SkillSpec from its colocated YAML template."""
    spec_path = Path(__file__).parent / "coder.yaml"
    data = yaml.safe_load(spec_path.read_text())
    return SkillSpec(
        name=data.get("role", "coder"),
        instructions=data.get("instructions", ""),
        tool_allow_list=[],
        hard_rules=data.get("hard_rules", []),
    )
