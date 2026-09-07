#!/usr/bin/env bash
# One headless turn with Gemini through the agy CLI.
#
#   agy_turn.sh <prompt-file> [--conv <id>] [--model <id>] [--cwd <dir>] [--detach <logdir>]
#
# Sync (default): prints agy's JSON result ({"conversation_id": ..., "response": ...}) on stdout.
# Detached: starts the turn with setsid/nohup, writes <logdir>/run.log (stream-json) and
# <logdir>/meta (start/end/exit), prints those two paths, returns at once.
set -uo pipefail

PROMPT_FILE="${1:?usage: agy_turn.sh <prompt-file> [--conv id] [--model id] [--cwd dir] [--detach logdir]}"; shift
CONV=""; MODEL="gemini-3.8-flash-high"; CWD="$PWD"; LOGDIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --conv) CONV="$2"; shift ;;
    --model) MODEL="$2"; shift ;;
    --cwd) CWD="$2"; shift ;;
    --detach) LOGDIR="$2"; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

PROMPT="$(cat "$PROMPT_FILE")"
ARGS=(-p "$PROMPT" --model "$MODEL" --dangerously-skip-permissions --print-timeout 240m)
[ -n "$CONV" ] && ARGS+=(--conversation "$CONV")
cd "$CWD" || exit 1

if [ -z "$LOGDIR" ]; then
  exec agy "${ARGS[@]}" --output-format json
fi

mkdir -p "$LOGDIR"
LOG="$LOGDIR/run.log"; META="$LOGDIR/meta"
echo "start=$(date -Iseconds) start_epoch=$(date +%s) cwd=$CWD model=$MODEL conv=${CONV:-new}" > "$META"
setsid nohup bash -c '
  agy "$@" --output-format stream-json > "$0" 2>&1; rc=$?
  echo "end=$(date -Iseconds) end_epoch=$(date +%s) exit=$rc" >> "$1"
' "$LOG" "$META" "${ARGS[@]}" > /dev/null 2>&1 < /dev/null &
echo "log=$LOG"
echo "meta=$META"
