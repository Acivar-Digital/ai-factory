#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

FROM_PHASE="${1:-coder}"
shift || true

./start.sh --from="$FROM_PHASE" "$@"
