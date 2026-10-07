#!/usr/bin/env python3
"""Append current coco panel instructions before launching either agent."""

import argparse
import json
import os
from pathlib import Path
import shlex
import sys

from _pane_codex_status import UsageClient
from _paths import state_dir


SCRIPTS = Path(__file__).resolve().parent


def panel_context(environ):
    slot = environ.get("COCO_SLOT", "1")
    if not slot.isascii() or not slot.isdigit() or int(slot) < 1:
        raise ValueError("COCO_SLOT must be a positive integer")
    logdir = Path(environ.get("COCO_LOG_DIR") or state_dir() / "logs").absolute()
    latest = logdir / ("latest.log" if slot == "1" else f"latest{slot}.log")
    values = {
        "COCO_SLOT": slot,
        "COCO_LOG_PATH": str(latest),
        "COCO_LOG_DIR": str(logdir),
        "COCO_COMMAND": str(SCRIPTS / "coco"),
    }
    # Spell out the destination so tools on a shared daemon need not inherit
    # the TUI process's environment to operate on the correct slot.
    command = shlex.join([
        "env", f"COCO_LOG_DIR={logdir}", f"COCO_SLOT={slot}",
        values["COCO_COMMAND"], "set-log",
    ])
    rules = (SCRIPTS / "AGENT_PANEL_INSTRUCTIONS.md").read_text()
    rules = rules.replace("<当前窗口的绑定命令>", command)
    header = "当前 coco 窗口（本次启动）：\n" + "\n".join(
        f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in values.items()
    )
    return header + "\n\n" + rules, values


def codex_args(binary, rules, values, mode, unsafe=False, inject=True):
    # Ask Codex to resolve its own user/project config, then append to existing
    # developer instructions without rewriting config.toml or AGENTS.md.
    args = [binary, "--no-alt-screen", "--add-dir", values["COCO_LOG_DIR"]]
    if unsafe:
        args.append("--dangerously-bypass-approvals-and-sandbox")
    if inject:
        client = UsageClient(binary)
        try:
            client.initialize()
            effective = client.call("config/read", {"cwd": os.getcwd(), "includeLayers": False})["config"]
        finally:
            client.close()
        existing = effective.get("developer_instructions") or ""
        instructions = existing + ("\n\n" if existing else "") + rules
        args += ["-c", "developer_instructions=" + json.dumps(instructions, ensure_ascii=False)]
    for key, value in values.items():
        args += ["-c", f"shell_environment_policy.set.{key}=" + json.dumps(value, ensure_ascii=False)]
    if mode != "new":
        args.append("resume")
        if mode == "continue":
            args.append("--last")
    return args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("codex", "claude"), required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--mode", choices=("new", "resume", "continue"), default="new")
    parser.add_argument("--unsafe", action="store_true")
    parser.add_argument("--no-instructions", action="store_true")
    options = parser.parse_args()
    try:
        rules, values = panel_context(os.environ)
        os.environ.update(values)
        if options.agent == "codex":
            args = codex_args(options.binary, rules, values, options.mode, options.unsafe, not options.no_instructions)
        else:
            args = [options.binary, "--add-dir", values["COCO_LOG_DIR"]]
            if not options.no_instructions:
                args += ["--append-system-prompt", rules]
            if options.unsafe:
                args.append("--dangerously-skip-permissions")
            if options.mode != "new":
                args.append("--" + options.mode)
        os.execv(options.binary, args)
    except (OSError, RuntimeError, TimeoutError, ValueError, KeyError):
        print("coco: Could not load panel rules or agent config. Check the CLI installation/config, or use coco open --no-instructions for an older CLI.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
