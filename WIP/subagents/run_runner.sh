#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

echo "=== Orchestrator Runner ==="
echo "Project: $(pwd)"
echo "State:   admin/subagents/runner_state.json"
echo "Config:  admin/subagents/runner.yaml"
echo ""

exec uv run python -m admin.subagents.runner "$@"
