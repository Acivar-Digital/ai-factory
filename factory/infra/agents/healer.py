"""Healer agent — JSON repair and diagnostics."""
from pathlib import Path
import yaml
from factory.infra.tools import SkillSpec

def build_healer_spec() -> SkillSpec:
    """Build the healer SkillSpec from its colocated YAML template."""
    spec_path = Path(__file__).parent / "healer.yaml"
    data = yaml.safe_load(spec_path.read_text())
    return SkillSpec(
        name=data.get("role", "healer"),
        instructions=data.get("instructions", ""),
        tool_allow_list=[],
        hard_rules=data.get("hard_rules", []),
    )
