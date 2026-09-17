#!/usr/bin/env bash
# 提示词走标准输入；后台任务保留独立日志与退出状态。
set -euo pipefail
usage='claude_turn.sh <prompt-file> --model <id> [--conv <id>] [--cwd <dir>] [--detach <new-logdir>] [-- <claude-options...>]'
if [ "${1:-}" = --help ]; then printf '%s\n' "$usage"; exit 0; fi
if [ $# -eq 0 ]; then printf 'usage: %s\n' "$usage" >&2; exit 2; fi
prompt_file=$1
shift
claude_model=''
conversation=''
run_cwd=$PWD
log_dir=''
extra=()
while [ $# -gt 0 ]; do
  case "$1" in
    --model|--conv|--cwd|--detach)
      if [ $# -lt 2 ] || [ -z "$2" ]; then
        printf 'missing value for %s\n' "$1" >&2; exit 2
      fi
      case "$1" in
        --model) claude_model=$2 ;;
        --conv) conversation=$2 ;;
        --cwd) run_cwd=$2 ;;
        --detach) log_dir=$2 ;;
      esac
      shift 2 ;;
    --) shift; extra=("$@"); break ;;
    *) printf 'unknown arg: %s\n' "$1" >&2; exit 2 ;;
  esac
done
if [ -z "$claude_model" ]; then
  echo '--model is required; use the model selected by the user' >&2; exit 2
fi
for arg in "${extra[@]}"; do
  case "${arg%%=*}" in
    --model|--resume|-r|--continue|-c|--input-format|--output-format|--print|-p|--bg|--background|--cloud|--remote-control|--permission-prompts)
      printf 'helper owns this option; use a direct CLI call: %s\n' "$arg" >&2; exit 2 ;;
  esac
done
claude_bin=$(command -v claude)
# 打开后再切换目录，避免相对路径含义改变，也避免提示词进入进程参数。
exec 3< "$prompt_file"
if [ -n "$log_dir" ]; then
  case "$log_dir" in /*) ;; *) log_dir="$PWD/$log_dir" ;; esac
fi
cd -- "$run_cwd"
args=(--print --model "$claude_model" --permission-prompts none --input-format text)
if [ -n "$conversation" ]; then args+=(--resume "$conversation"); fi
args+=("${extra[@]}")
if [ -z "$log_dir" ]; then
  exec "$claude_bin" "${args[@]}" --output-format json <&3 3<&-
fi
command -v setsid >/dev/null
command -v nohup >/dev/null
umask 077
mkdir -m 700 -- "$log_dir"
cat <&3 > "$log_dir/prompt.txt"
exec 3<&-
meta_file="$log_dir/meta"
printf 'start=%s\ncwd=%s\nmodel=%s\nconv=%s\n' "$(date -Iseconds)" "$PWD" "$claude_model" "${conversation:-new}" > "$meta_file"
setsid nohup bash -c '
  log_dir=$1
  shift
  "$@" --output-format stream-json --verbose < "$log_dir/prompt.txt" > "$log_dir/run.log" 2>&1
  result=$?
  printf "end=%s exit=%s\n" "$(date -Iseconds)" "$result" >> "$log_dir/meta"
  exit "$result"
' claude-turn "$log_dir" "$claude_bin" "${args[@]}" >/dev/null 2>&1 </dev/null &
run_pid=$!
printf 'pid=%s\n' "$run_pid" >> "$meta_file"
printf 'log=%s\nmeta=%s\npid=%s\n' "$log_dir/run.log" "$meta_file" "$run_pid"
