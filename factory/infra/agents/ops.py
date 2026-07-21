"""Ops agent — git push and finalization."""
from pathlib import Path
import yaml
from factory.infra.tools import SkillSpec

def build_ops_spec() -> SkillSpec:
    """Build the ops SkillSpec from its colocated YAML template."""
    spec_path = Path(__file__).parent / "ops.yaml"
    data = yaml.safe_load(spec_path.read_text())
    return SkillSpec(
        name=data.get("role", "ops"),
        instructions=data.get("instructions", ""),
        tool_allow_list=[],
        hard_rules=data.get("hard_rules", []),
    )
