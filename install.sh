#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo 'Install Python 3.9+ first.' >&2; exit 1; }
exec python3 "$DIR/install.py" "$@"
