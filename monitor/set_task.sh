#!/usr/bin/env bash
# Write a Chinese task description for a monitor slot. The right-top pane
# of the matching monitor reads this file and renders it.
#
# Usage:
#   set_task.sh [--slot N] [--pid PID] [--log PATH] [--project NAME] [--note TEXT] '任务标题'
#   set_task.sh [--slot N] --clear         # remove the current task
#
# All flags are optional except the title (or --clear).
# Defaults:
#   --slot     1
#   --project  basename of $PWD
#   --log      $COCO_LOG_PATH (if set)
#
# Output file: $LOGDIR/task_slot${SLOT}.md (overwritten each call).
set -euo pipefail

DEFAULT_STATE="${COCO_DATA_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/cocopane}"
LOGDIR="${COCO_LOG_DIR:-$DEFAULT_STATE/logs}"

SLOT="${COCO_SLOT:-1}"
PID=""
LOG="${COCO_LOG_PATH:-}"
PROJECT="$(basename "$PWD")"
NOTE=""
TITLE=""
CLEAR=0

while (( $# > 0 )); do
  case "$1" in
    --slot)    SLOT="$2"; shift 2 ;;
    --pid)     PID="$2"; shift 2 ;;
    --log)     LOG="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --note)    NOTE="$2"; shift 2 ;;
    --clear)   CLEAR=1; shift ;;
    -h|--help)
      sed -n '2,15p' "$0"; exit 0 ;;
    --) shift; break ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)  TITLE="$1"; shift ;;
  esac
done

if ! [[ "$SLOT" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: --slot needs a positive integer (got: '$SLOT')" >&2
  exit 2
fi

TASKFILE="$LOGDIR/task_slot${SLOT}.md"
mkdir -p "$LOGDIR"

if (( CLEAR )); then
  rm -f "$TASKFILE"
  echo "cleared: $TASKFILE"
  exit 0
fi

if [[ -z "$TITLE" ]]; then
  echo "ERROR: title required (or pass --clear)" >&2
  echo "usage: ${COCO_CMD:-$0} [--slot N] [--pid PID] [--log PATH] [--project NAME] [--note TEXT] '任务标题'" >&2
  exit 2
fi

# Resolve relative log paths against PWD so the user can pass `logs/foo.log`.
if [[ -n "$LOG" && "$LOG" != /* ]]; then
  LOG="$PWD/$LOG"
fi

started="$(date '+%Y-%m-%dT%H:%M:%S%z')"

# Write atomically (write to .tmp then mv) so the pane never reads a half-
# written file. Each field is a single line — \n in user input is preserved
# but downstream readers split on the first '='.
tmp="$TASKFILE.tmp.$$"
{
  printf 'title=%s\n'   "$TITLE"
  printf 'project=%s\n' "$PROJECT"
  printf 'pid=%s\n'     "$PID"
  printf 'log=%s\n'     "$LOG"
  printf 'started=%s\n' "$started"
  printf 'note=%s\n'    "$NOTE"
} >"$tmp"
mv "$tmp" "$TASKFILE"

echo "wrote: $TASKFILE"
echo "  title  : $TITLE"
[[ -n "$PROJECT" ]] && echo "  project: $PROJECT"
[[ -n "$PID"     ]] && echo "  pid    : $PID"
[[ -n "$LOG"     ]] && echo "  log    : $LOG"
[[ -n "$NOTE"    ]] && echo "  note   : $NOTE"
