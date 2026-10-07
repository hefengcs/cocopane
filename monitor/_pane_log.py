#!/usr/bin/env python3
"""Follow only this slot's log; reap tail on retarget, pane close or SIGTERM."""
import argparse
import signal
import subprocess
import sys
import time

from _paths import latest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, required=True)
    args = parser.parse_args()
    latest = latest_path(args.slot)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGHUP, lambda *_: sys.exit(0))
    child, current = None, None
    try:
        while True:
            try:
                target = latest.resolve(strict=True)
                if not target.is_file():
                    target = None
            except (OSError, RuntimeError):
                target = None
            if target != current or (child is not None and child.poll() is not None):
                if child is not None:
                    child.terminate()
                    child.wait(timeout=3)
                    child = None
                current = target
                print("\033[H\033[2J", end="", flush=True)
                if target:
                    print(f"Log · slot {args.slot}\n{target}", flush=True)
                    child = subprocess.Popen(["tail", "-n", "100", "-F", "--", str(target)])
            if child is None:
                print(f"\033[H\033[2JLog · slot {args.slot}\nWaiting for a task log.\nUse: coco set-log /path/to/job.log", end="", flush=True)
            time.sleep(1)
    finally:
        if child is not None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
