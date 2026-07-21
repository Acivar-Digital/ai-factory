"""Planner agent — reasoning and planning."""
from pathlib import Path
import yaml
from factory.infra.tools import SkillSpec

def build_planner_spec() -> SkillSpec:
    """Build the planner SkillSpec from its colocated YAML template."""
    spec_path = Path(__file__).parent / "planner.yaml"
    data = yaml.safe_load(spec_path.read_text())
    return SkillSpec(
        name=data.get("role", "planner"),
        instructions=data.get("instructions", ""),
        tool_allow_list=[],
        hard_rules=data.get("hard_rules", []),
    )
