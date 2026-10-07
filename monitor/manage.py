#!/usr/bin/env python3
"""Small read-only diagnostics and explicitly requested session management."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from _paths import latest_path, log_dir, socket_name, state_dir


HELP = """CocoPane — agent, account usage, GPU and task logs in one terminal

  coco open [codex|claude] [--resume|--continue] [--slot N]
            [--no-gpu] [--no-usage] [--no-instructions] [--detach] [--unsafe]
  coco codex|claude [options]       Shortcut for open
  coco doctor [--agent codex|claude] Check dependencies without changing them
  coco status                      List sessions, current log and state directory
  coco set-log [--slot N] FILE      Follow an existing log (defaults to current slot)
  coco set-task [options] TITLE     Optional task metadata for coco tasks
  coco tasks                       Show registered task titles
  coco kill [SESSION|--all]         List, or explicitly stop coco sessions
  coco --version

Linux / WSL2, Python 3.9+, Bash, tmux 3.0+ and GNU coreutils required.
Install and log in to Codex or Claude separately. NVIDIA GPU is optional.
Default agent permissions and authentication are preserved; --unsafe is opt-in.
Layout is 60% agent / 40% dashboard. Wheel scrolls; q exits history.
Xshell: Shift-right-click or Shift-Insert pastes; Ctrl-b m toggles mouse capture.
Ctrl-b d detaches. Ctrl-b o switches panes. See README.md for installation.
"""


def tmux(*args):
    return subprocess.run(["tmux", "-L", socket_name(), *args], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def sessions():
    if not shutil.which("tmux"):
        return []
    return [s for s in tmux("list-sessions", "-F", "#{session_name}").stdout.splitlines() if s.startswith("coco-")]


def doctor(agent=None):
    good = sys.platform == "linux" and sys.version_info >= (3, 9)
    print(f"Python: {sys.version.split()[0]} · platform: {sys.platform}")
    for name in ("bash", "tmux", "readlink", "tail", "ln"):
        path = shutil.which(name)
        print(f"{'OK' if path else 'MISSING'} {name}: {path or 'install required'}")
        good = good and bool(path)
    if shutil.which("tmux"):
        version = subprocess.run(["tmux", "-V"], capture_output=True, text=True).stdout.strip()
        print(version)
        import re
        match = re.search(r"(\d+)\.(\d+)", version)
        if not match or tuple(map(int, match.groups())) < (3, 0):
            good = False
            print("tmux 3.0+ required")
    available = []
    for name in ("codex", "claude"):
        path = os.environ.get(name.upper() + "_BIN") or shutil.which(name)
        present = bool(path and os.access(path, os.X_OK))
        available.append(present)
        print(f"{'OK' if present else 'OPTIONAL/MISSING'} {name}: {path or 'not installed'}")
        if agent == name and not present:
            good = False
    if agent is None and not any(available):
        good = False
    print("GPU: " + ("nvidia-smi found" if shutil.which("nvidia-smi") else "optional; CPU-only fallback available"))
    print(f"State: {state_dir()}\nLogs: {log_dir()}\nTmux socket: {socket_name()}")
    print("No login test performed. Sign in using the agent's own CLI.")
    if not good:
        print("Ubuntu/Debian/WSL: sudo apt install tmux python3 bash coreutils")
        print("Install Codex/Claude separately; see README.md.")
    return 0 if good else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("--help", "-h"):
        print(HELP)
        return 0
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", nargs="?", default="help")
    parser.add_argument("rest", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command in ("help", "--help", "-h"):
        if args.rest == ["open"]:
            os.execv(sys.executable, [sys.executable, str(Path(__file__).with_name("open_monitor.py")), "--help"])
        print(HELP)
        return 0
    if args.command == "doctor":
        p = argparse.ArgumentParser(prog="coco doctor")
        p.add_argument("--agent", choices=("codex", "claude"))
        return doctor(p.parse_args(args.rest).agent)
    if args.command == "status":
        print("Sessions:\n" + ("\n".join(sessions()) or "(none)"))
        slot = os.environ.get("COCO_SLOT", "1")
        if not slot.isascii() or not slot.isdigit() or int(slot) < 1:
            parser.error("COCO_SLOT must be a positive integer")
        latest = latest_path(slot)
        print(f"Logs: {log_dir()}\nSlot {slot}: {latest}")
        if latest.is_symlink():
            print("Target: " + os.readlink(latest))
        return 0
    if args.command == "tasks":
        for file in sorted(log_dir().glob("task_slot*.md")):
            fields = dict(line.split("=", 1) for line in file.read_text().splitlines() if "=" in line)
            print(file.stem + ": " + fields.get("title", "(untitled)"))
        return 0
    if args.command == "kill":
        current = sessions()
        if not args.rest:
            print("\n".join(current) or "(no coco sessions)")
            print("Use coco kill SESSION or coco kill --all to stop them.")
            return 0
        if len(args.rest) != 1:
            parser.error("kill takes an exact session name or --all")
        targets = current if args.rest == ["--all"] else args.rest
        for target in targets:
            if target not in current:
                parser.error("not an existing coco session: " + target)
            result = tmux("kill-session", "-t", "=" + target)
            if result.returncode:
                print("Could not stop " + target, file=sys.stderr)
                return 1
            print("Stopped " + target)
        return 0
    print("Unknown command.\n" + HELP, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
