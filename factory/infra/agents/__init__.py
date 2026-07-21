"""Agent implementations — one module per role, colocated with YAML templates."""
from factory.infra.agents.planner import build_planner_spec
from factory.infra.agents.coder import build_coder_spec
from factory.infra.agents.supervisor import build_supervisor_plan_spec, build_supervisor_review_spec
from factory.infra.agents.red_team import build_red_team_spec
from factory.infra.agents.ops import build_ops_spec
from factory.infra.agents.healer import build_healer_spec

__all__ = [
    "build_planner_spec",
    "build_coder_spec",
    "build_supervisor_plan_spec",
    "build_supervisor_review_spec",
    "build_red_team_spec",
    "build_ops_spec",
    "build_healer_spec",
]
