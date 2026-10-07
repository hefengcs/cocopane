#!/usr/bin/env bash
# Point $LOGDIR/latest{N}.log at the given log file (symlink).
# Usage: set_latest_log.sh [--slot N] path/to/job.log
#   default slot: $COCO_SLOT, otherwise 1
#   slot 1 → $LOGDIR/latest.log
#   slot 2,3,...     → $LOGDIR/latest2.log, $LOGDIR/latest3.log, ...
# $LOGDIR is COCO_LOG_DIR or the user's coco state directory.
set -euo pipefail
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo 'Usage: coco set-log [--slot N] FILE (default slot: $COCO_SLOT, else 1)'
  exit 0
fi

DEFAULT_STATE="${COCO_DATA_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/cocopane}"
LOGDIR="${COCO_LOG_DIR:-$DEFAULT_STATE/logs}"

SLOT="${COCO_SLOT:-1}"
if [[ "${1:-}" == "--slot" ]]; then
  SLOT="${2:-}"
  (( $# >= 2 )) || { echo 'ERROR: --slot requires a number' >&2; exit 2; }
  shift 2
fi
if ! [[ "$SLOT" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: slot must be a positive integer (got: '${SLOT}')" >&2
  exit 2
fi

if (( $# != 1 )); then
  echo "usage: ${COCO_CMD:-$0} [--slot N] <path-to-log>" >&2
  exit 2
fi

if [[ "$SLOT" == "1" ]]; then
  LATEST="$LOGDIR/latest.log"
else
  LATEST="$LOGDIR/latest${SLOT}.log"
fi

target="$1"

# Relative paths resolve against the caller's cwd — they typed something
# they can see with `ls` from there.
if [[ "$target" != /* ]]; then
  target="$PWD/$target"
fi

if [[ ! -f "$target" ]]; then
  echo "ERROR: log file does not exist or is not a regular file: $target" >&2
  echo "       (create it first, e.g.  : > \"$target\")" >&2
  exit 1
fi

mkdir -p "$LOGDIR"
target="$(readlink -f -- "$target")"
if [[ -e "$LATEST" && ! -L "$LATEST" ]]; then
  echo "ERROR: refusing to replace existing non-symlink log: $LATEST" >&2
  exit 1
fi

# Replace the link itself, never follow a destination directory symlink.
ln -sfnT -- "$target" "$LATEST"

echo "$(basename "$LATEST") → $target"
