#!/usr/bin/env bash
# arena.sh <run_dir> -- cmd...
# Runs cmd inside private mount+pid namespaces: /arena = <run_dir>/work, /root = <run_dir>/home
# (skills pre-copied there), /tmp, /home/user, /mnt hidden.
set -euo pipefail
run_dir=$(realpath "$1"); shift; [ "$1" = -- ] && shift
mkdir -p "$run_dir/work" "$run_dir/home/.claude/skills" "$run_dir/home/.ccr"
exec unshare -m -p -f --mount-proc --propagation private bash -c '
  set -e
  run_dir=$1; shift
  mount --bind "$run_dir/work" /arena
  mount --bind -o ro /root/.ccr "$run_dir/home/.ccr"
  mount --rbind "$run_dir/home" /root
  mount -t tmpfs tmpfs /tmp
  mount -t tmpfs tmpfs /home/user
  mount -t tmpfs tmpfs /mnt 2>/dev/null || true
  cd /arena
  exec env -u CLAUDE_CODE_SYNC_PLUGINS -u CLAUDE_CODE_SYNC_SKILLS -u CLAUDE_ADDITIONAL_DIRECTORIES -u CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD "$@"
' arena "$run_dir" "$@"
