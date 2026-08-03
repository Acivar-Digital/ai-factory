"""Agent role templates for the intern -> engineer -> senior pipeline.

Only these three roles are live (see ``factory.infra.control.SKILL_MAP``).
Each role's frozen SkillSpec is built from its colocated YAML template by
``factory.infra.tools.build_skill_spec``; intern/engineer/senior have no
per-role Python modules (they use the YAML fallback path), so there is
nothing to import at module level — the three role names are the package's
public surface.
"""
__all__ = ["intern", "engineer", "senior"]
