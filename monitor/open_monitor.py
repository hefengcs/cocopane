#!/usr/bin/env python3
"""Launch an isolated tmux dashboard using the user's installed agent CLI."""
import argparse
from datetime import datetime
import fcntl
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import uuid

from _paths import SCRIPTS, latest_path, log_dir, socket_name, state_dir


def tmux(*args, check=True):
    return subprocess.run(["tmux", "-L", socket_name(), "-f", str(SCRIPTS / "tmux.conf"), *args],
                          check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def shell_command(*args):
    return shlex.join(str(arg) for arg in args)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", nargs="?", default="codex", choices=("codex", "claude"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true", help="Open the agent's session picker")
    mode.add_argument("--continue", dest="continue_last", action="store_true", help="Continue the last session")
    parser.add_argument("--slot", type=int, help="Log slot; by default choose a free one")
    parser.add_argument("--detach", action="store_true", help="Create without attaching (also useful over automation)")
    parser.add_argument("--no-gpu", action="store_true", help="Hide the GPU pane")
    parser.add_argument("--no-usage", action="store_true", help="Hide the Codex account quota pane")
    parser.add_argument("--no-instructions", action="store_true", help="Skip the injected log maintenance rules")
    parser.add_argument("--unsafe", action="store_true", help="Explicitly disable the agent's approval/sandbox checks")
    args = parser.parse_args(argv)
    if args.slot is not None and args.slot < 1:
        parser.error("--slot must be positive")
    return args


def sync_environment(session):
    # Session environment is inherited by future panes. Do not embed API keys
    # in pane commands, save them to files, or inherit stale values from another launch.
    inherited = tmux("show-environment", "-g").stdout.splitlines()
    names = {line.lstrip("-").split("=", 1)[0] for line in inherited}
    excluded = {"TMUX", "TMUX_PANE", "STY"}
    for name in sorted(names | os.environ.keys()):
        if name in excluded or name not in os.environ:
            tmux("set-environment", "-r", "-t", session, name)
        else:
            tmux("set-environment", "-t", session, name, os.environ[name])


def launch(args):
    if sys.version_info < (3, 9):
        raise RuntimeError("Python 3.9+ is required")
    if sys.platform != "linux":
        raise RuntimeError("This release supports Linux and WSL2. macOS/native Windows are not validated.")
    for dependency in ("tmux", "bash", "readlink", "tail"):
        if not shutil.which(dependency):
            raise RuntimeError(f"Missing {dependency}; run coco doctor for installation hints")
    binary = os.environ.get(args.agent.upper() + "_BIN") or shutil.which(args.agent)
    if not binary or not Path(binary).is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError(f"Install and sign in to {args.agent} first, or set {args.agent.upper()}_BIN")
    binary = str(Path(binary).absolute())
    cwd = str(Path(os.environ.get("COCO_CWD") or os.getcwd()).resolve())
    if not Path(cwd).is_dir():
        raise RuntimeError("COCO_CWD does not name a directory")
    state_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    log_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    cols, rows = shutil.get_terminal_size((120, 40))
    if not args.detach and (cols < 80 or rows < 24):
        raise RuntimeError("Use a terminal at least 80 columns × 24 rows, or hide panes with --no-gpu --no-usage")
    lock_name = hashlib.sha256(socket_name().encode()).hexdigest()[:16]
    session = None
    # Reserve a slot while creating its session; simultaneous launches cannot collide.
    with (state_dir() / f"launch-{lock_name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        listing = tmux("list-sessions", "-F", "#{session_name}", check=False).stdout
        used = {int(m.group(1)) for m in re.finditer(r"^coco-(?:codex|claude)-slot(\d+)-", listing, re.M)}
        slot = args.slot or next(n for n in range(1, len(used) + 2) if n not in used)
        if slot in used:
            raise RuntimeError(f"Slot {slot} is already in use; omit --slot to choose a free slot")
        session = f"coco-{args.agent}-slot{slot}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        try:
            left = tmux("new-session", "-d", "-s", session, "-n", "dash", "-x", str(cols), "-y", str(rows),
                        "-c", cwd, "-P", "-F", "#{pane_id}", "sleep 86400").stdout.strip()
            sync_environment(session)
            for name, value in {"COCO_SLOT": str(slot), "COCO_LOG_DIR": str(log_dir()),
                                "COCO_LOG_PATH": str(latest_path(slot)), "COCO_COMMAND": str(SCRIPTS / "coco")}.items():
                tmux("set-environment", "-t", session, name, value)
            tmux("set-option", "-t", session, "mouse", "on")
            tmux("set-window-option", "-t", session, "remain-on-exit", "on")
            mode = "resume" if args.resume else "continue" if args.continue_last else "new"
            agent_command = [sys.executable, SCRIPTS / "_launch_agent.py", "--agent", args.agent,
                             "--binary", binary, "--mode", mode]
            if args.unsafe:
                agent_command.append("--unsafe")
            if args.no_instructions:
                agent_command.append("--no-instructions")
            commands = []
            if args.agent == "codex" and not args.no_usage:
                commands.append(shell_command(sys.executable, SCRIPTS / "_pane_codex_status.py", "--codex", binary))
            if not args.no_gpu:
                commands.append(shell_command(sys.executable, SCRIPTS / "_pane_gpu.py"))
            commands.append(shell_command(sys.executable, SCRIPTS / "_pane_log.py", "--slot", slot))
            panes = []
            for index, command in enumerate(commands):
                target = left if index == 0 else panes[-1]
                flags = ["-h", "-p", "40"] if index == 0 else ["-v", "-p", str(round(100 * (len(commands)-index) / (len(commands)-index+1))) ]
                panes.append(tmux("split-window", "-t", target, *flags, "-c", cwd, "-P", "-F", "#{pane_id}", command).stdout.strip())
            sockpath = tmux("display-message", "-p", "-t", left, "#{socket_path}").stdout.strip()
            resize = shell_command("bash", SCRIPTS / "_resize_layout.sh", sockpath, panes[0])
            for hook in ("client-attached", "client-resized", "after-resize-window"):
                tmux("set-hook", "-t", session, hook, "run-shell " + shlex.quote(resize))
            tmux("bind-key", "-T", "prefix", "m", "if-shell", "-F", "#{mouse}",
                 'set-option mouse off; display-message "Terminal mouse: local selection/paste. Ctrl-b m restores scrolling"',
                 'set-option mouse on; display-message "Wheel: scroll. Xshell Shift-right-click / Shift-Insert: paste"')
            tmux("respawn-pane", "-k", "-t", left, "-c", cwd, shell_command(*agent_command))
            tmux("select-pane", "-t", left)
        except Exception:
            tmux("kill-session", "-t", "=" + session, check=False)
            raise
    print(f"Created {session} (slot {slot})", flush=True)
    print("Attach: " + shell_command("tmux", "-L", socket_name(), "attach", "-t", session), flush=True)
    if not args.detach:
        env = dict(os.environ)
        env.pop("TMUX", None)
        os.execvpe("tmux", ["tmux", "-L", socket_name(), "attach", "-t", session], env)
    return session


def main():
    try:
        launch(parse_args())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        # A failed tmux environment command could contain credentials in argv.
        if isinstance(exc, subprocess.CalledProcessError):
            message = "tmux could not create the dashboard; check coco doctor and terminal size"
        else:
            message = str(exc)
        print("coco: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
