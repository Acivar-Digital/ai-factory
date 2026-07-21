#!/usr/bin/env bash
set -euo pipefail
echo "[DEPRECATED] continue.sh is deprecated — use run.sh instead." >&2
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FROM_PHASE="${1:-coder}"
shift || true
exec "$SCRIPT_DIR/run.sh" --from="$FROM_PHASE" "$@"
