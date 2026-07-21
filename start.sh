#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/factory/infra/.env"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="$SCRIPT_DIR/.env"
fi

ENV_CWD="$SCRIPT_DIR"
if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r k v; do
        k="$(echo "$k" | tr -d ' ')"
        v="$(echo "$v" | tr -d ' "')"
        case "$k" in
            CWD) ENV_CWD="$v" ;;
        esac
    done < "$ENV_FILE"
fi

PKG_DIR="$SCRIPT_DIR/factory"
ORCH_ROOT="$PKG_DIR/orch"

FRESH=0
FROM_FLAG=""
STOP_AFTER_FLAG=""
RESUME_ACTIVE=0
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --fresh) FRESH=1 ;;
        --from) ;;
        --from=*) FROM_FLAG="${arg#--from=}" ;;
        --stop-after) ;;
        --stop-after=*) STOP_AFTER_FLAG="${arg#--stop-after=}" ;;
        --resume) RESUME_ACTIVE=1 ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done

FROM_ACTIVE=0
if [ -n "$FROM_FLAG" ]; then
    FROM_ACTIVE=1
fi
CONTINUATION_ACTIVE=0
if [ "$FROM_ACTIVE" -eq 1 ] || [ -n "$STOP_AFTER_FLAG" ] || [ "$RESUME_ACTIVE" -eq 1 ]; then
    CONTINUATION_ACTIVE=1
fi

PROMPT_FILE="$PKG_DIR/prompt/user_prompt.md"
BD_ID="${POSITIONAL[0]:-factory-run}"

SESSION="ai-factory"
RUN_LOG="$ORCH_ROOT/logs/runtime/run.log"
STATUS="$PKG_DIR/STATUS.md"

if command -v tmux >/dev/null 2>&1 && [ -n "${TMUX:-}" ]; then
    tmux kill-session -t "$SESSION" 2>/dev/null || true
fi

echo "[WIPE] clearing logs..."
rm -rf "$ORCH_ROOT/logs"

if [ "$CONTINUATION_ACTIVE" -eq 1 ]; then
    echo "[WIPE] continuation mode: preserving prior artefacts"
else
    echo "[WIPE] clearing runtime dirs + old artefacts..."
    rm -rf "$ORCH_ROOT/reports" \
           "$ORCH_ROOT/context" \
           "$ORCH_ROOT/temp" \
           "$ORCH_ROOT/prompt"
    rm -rf "$PKG_DIR/artefacts/workplan"
    rm -rf "$PKG_DIR/artefacts/history"
    rm -f "$PKG_DIR/STATUS.md"
    rm -rf "$PKG_DIR/customised"
    rm -rf "$PKG_DIR/reports" "$PKG_DIR/temp"
fi

RUN_ARGS="--bd $BD_ID"
if [ "$FROM_ACTIVE" -eq 1 ]; then
    RUN_ARGS="$RUN_ARGS --from $FROM_FLAG"
fi
if [ -n "$STOP_AFTER_FLAG" ]; then
    RUN_ARGS="$RUN_ARGS --stop-after $STOP_AFTER_FLAG"
fi
if [ "$RESUME_ACTIVE" -eq 1 ]; then
    RUN_ARGS="$RUN_ARGS --resume"
fi

mkdir -p "$ORCH_ROOT/logs/runtime"
PYTHONPATH="$SCRIPT_DIR" uv run python -m factory.infra.runner $RUN_ARGS
