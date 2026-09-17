#!/usr/bin/env bash
# 通过 agy 执行一轮；模型由调用者明确提供。
# 后台模式使用独立日志目录，记录 PID 和退出状态。
set -euo pipefail

usage='agy_turn.sh <prompt-file> --model <id> [--conv <id>] [--cwd <dir>] [--detach <new-logdir>]'
if [ $# -eq 0 ]; then
  echo "usage: $usage" >&2
  exit 2
fi
prompt_file=$1
shift
conversation=''
gemini_model=''
run_cwd=$PWD
log_dir=''
while [ $# -gt 0 ]; do
  case "$1" in
    --conv|--model|--cwd|--detach)
      if [ $# -lt 2 ] || [ -z "$2" ]; then
        echo "missing value for $1" >&2
        exit 2
      fi
      case "$1" in
        --conv) conversation=$2 ;;
        --model) gemini_model=$2 ;;
        --cwd) run_cwd=$2 ;;
        --detach) log_dir=$2 ;;
      esac
      shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$gemini_model" ]; then
  echo '--model is required; use the model selected by the user' >&2
  exit 2
fi
prompt=$(cat -- "$prompt_file")
command -v agy >/dev/null
args=(-p "$prompt" --model "$gemini_model" --dangerously-skip-permissions --print-timeout 240m)
if [ -n "$conversation" ]; then args+=(--conversation "$conversation"); fi
# 日志相对路径以调用位置为准，与工作目录参数无关。
if [ -n "$log_dir" ]; then
  case "$log_dir" in /*) ;; *) log_dir="$PWD/$log_dir" ;; esac
fi
cd -- "$run_cwd"
if [ -z "$log_dir" ]; then
  exec agy "${args[@]}" --output-format json
fi
command -v setsid >/dev/null
command -v nohup >/dev/null
mkdir -m 700 -- "$log_dir"
log_file="$log_dir/run.log"
meta_file="$log_dir/meta"
printf 'start=%s cwd=%s model=%s conv=%s\n' "$(date -Iseconds)" "$PWD" "$gemini_model" "${conversation:-new}" > "$meta_file"
setsid nohup bash -c '
  log_file=$1
  meta_file=$2
  shift 2
  agy "$@" --output-format stream-json > "$log_file" 2>&1
  result=$?
  printf "end=%s exit=%s\n" "$(date -Iseconds)" "$result" >> "$meta_file"
  exit "$result"
' agy-turn "$log_file" "$meta_file" "${args[@]}" > /dev/null 2>&1 < /dev/null &
run_pid=$!
printf 'pid=%s\n' "$run_pid" >> "$meta_file"
printf 'log=%s\nmeta=%s\npid=%s\n' "$log_file" "$meta_file" "$run_pid"
