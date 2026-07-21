"""Supervisor agents — plan and review gating."""
from pathlib import Path
import yaml
from factory.infra.tools import SkillSpec

def build_supervisor_plan_spec() -> SkillSpec:
    """Build the supervisor_plan SkillSpec from its colocated YAML template."""
    spec_path = Path(__file__).parent / "supervisor_plan.yaml"
    data = yaml.safe_load(spec_path.read_text())
    return SkillSpec(
        name=data.get("role", "supervisor_plan"),
        instructions=data.get("instructions", ""),
        tool_allow_list=[],
        hard_rules=data.get("hard_rules", []),
    )

def build_supervisor_review_spec() -> SkillSpec:
    """Build the supervisor_review SkillSpec from its colocated YAML template."""
    spec_path = Path(__file__).parent / "supervisor_review.yaml"
    data = yaml.safe_load(spec_path.read_text())
    return SkillSpec(
        name=data.get("role", "supervisor_review"),
        instructions=data.get("instructions", ""),
        tool_allow_list=[],
        hard_rules=data.get("hard_rules", []),
    )
