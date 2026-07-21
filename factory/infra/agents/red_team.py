"""Red Team agent — adversarial auditing."""
from pathlib import Path
import yaml
from factory.infra.tools import SkillSpec

def build_red_team_spec() -> SkillSpec:
    """Build the red_team SkillSpec from its colocated YAML template."""
    spec_path = Path(__file__).parent / "red_team.yaml"
    data = yaml.safe_load(spec_path.read_text())
    return SkillSpec(
        name=data.get("role", "red_team"),
        instructions=data.get("instructions", ""),
        tool_allow_list=[],
        hard_rules=data.get("hard_rules", []),
    )
