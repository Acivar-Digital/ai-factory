#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

# Setup paths so we can import TEST/agent_guardrail.py and admin/git_push_agent.py
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(WORKSPACE_ROOT))

# Prevent fastmcp stdout logging corruption
import logging  # noqa: E402

logging.basicConfig(level=logging.ERROR)
logging.getLogger("fastmcp").setLevel(logging.ERROR)

from fastmcp import FastMCP  # noqa: E402

from TEST.agent_guardrail import checkpoint, validate  # noqa: E402

mcp = FastMCP(os.getenv("MCP_NAME", "git-guardrail"))

def _resolve_path(relative_path: str) -> Path:
    root = WORKSPACE_ROOT.resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Path escape detected: {relative_path}")
    return target

@mcp.tool()
def checkpoint_file(
    relative_path: Annotated[str, "File path relative to repository root."]
) -> dict[str, Any]:
    """Create a checkpoint snapshot of the specified file before making edits."""
    try:
        target_path = _resolve_path(relative_path)
        backup = checkpoint(str(target_path))
        if backup:
            return {"success": True, "checkpoint_path": backup, "message": f"Successfully checkpointed {relative_path}"}
        return {"success": False, "message": f"Failed to checkpoint {relative_path}"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@mcp.tool()
def validate_file(
    relative_path: Annotated[str, "File path relative to repository root."]
) -> dict[str, Any]:
    """Validate python file syntax and run ruff checks/formatting sanitization after making edits."""
    try:
        target_path = _resolve_path(relative_path)
        res = validate(str(target_path))
        return res
    except Exception as e:
        return {"success": False, "message": str(e)}

@mcp.tool()
def git_release_push() -> dict[str, Any]:
    """Execute the full git push release pipeline (bumps version, logs changes, stages files, commits and pushes)."""
    import time
    time.sleep(2)
    backoffs = [90, 120, 240]
    for attempt, delay in enumerate(backoffs + [0], start=1):
        try:
            cmd = ["uv", "run", "python", "admin/git_push_agent.py"]
            res = subprocess.run(
                cmd,
                cwd=str(WORKSPACE_ROOT),
                capture_output=True,
                text=True,
                timeout=300
            )
            if res.returncode == 0:
                return {
                    "success": True,
                    "message": "Git release pipeline completed successfully.",
                    "stdout": res.stdout,
                }

            if attempt <= len(backoffs):
                print(f"⚠️ Git release pipeline failed with exit code {res.returncode}. Retrying in {delay}s (attempt {attempt}/{len(backoffs)})...", file=sys.stderr)
                time.sleep(delay)
                continue

            # Exhausted retries
            print("🚨 Git release pipeline failed after retries. Shutting down and reporting.", file=sys.stderr)
            print(f"STDOUT:\n{res.stdout}", file=sys.stderr)
            print(f"STDERR:\n{res.stderr}", file=sys.stderr)
            sys.exit(res.returncode if res.returncode else 1)
        except Exception as e:
            if attempt <= len(backoffs):
                print(f"⚠️ Exception during git release pipeline: {e}. Retrying in {delay}s (attempt {attempt}/{len(backoffs)})...", file=sys.stderr)
                time.sleep(delay)
                continue
            print(f"🚨 Exception during git release pipeline after retries: {e}. Shutting down and reporting.", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    mcp.run()
