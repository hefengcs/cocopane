#!/usr/bin/env bash
# Restore the monitor's 60/40 split after attaching or resizing a client.
set -euo pipefail
SOCKET="$1"
PANE="$2"
WIDTH=$(tmux -S "$SOCKET" display-message -p -t "$PANE" '#{window_width}')
[[ "$WIDTH" =~ ^[0-9]+$ ]] || exit 0
RIGHT_WIDTH=$((WIDTH * 40 / 100))
(( RIGHT_WIDTH > 0 )) || exit 0
tmux -S "$SOCKET" resize-pane -t "$PANE" -x "$RIGHT_WIDTH"
