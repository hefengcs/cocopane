#!/usr/bin/env python3
"""Read Codex account quotas through app-server; never start an inference turn."""

import argparse
from datetime import datetime
import json
import math
import os
import selectors
import shutil
import signal
import subprocess
import sys
import time
import unicodedata


class UsageClient:
    def __init__(self, binary):
        self.process = subprocess.Popen(
            [binary, "app-server", "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = b""
        self.request_id = 0

    def call(self, method, params=None):
        self.request_id += 1
        request = {"id": self.request_id, "method": method}
        if params is not None:
            request["params"] = params
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        self.process.stdin.flush()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                response = json.loads(line)
                if response.get("id") != self.request_id:
                    continue
                if "error" in response:
                    raise RuntimeError("usage unavailable")
                return response["result"]
            if not self.selector.select(max(0, deadline - time.monotonic())):
                break
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("app-server disconnected")
            self.buffer += chunk
        raise TimeoutError("app-server timeout")

    def initialize(self):
        self.call("initialize", {
            "clientInfo": {"name": "coco_usage_monitor", "version": "1.0"},
        })
        self.process.stdin.write(b'{"method":"initialized"}\n')
        self.process.stdin.flush()

    def close(self):
        self.selector.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in (self.process.stdin, self.process.stdout):
            stream.close()


def period(minutes, fallback):
    if not isinstance(minutes, (int, float)) or minutes <= 0:
        return fallback
    if minutes % 1440 == 0:
        return f"{minutes / 1440:g}天额度"
    if minutes % 60 == 0:
        return f"{minutes / 60:g}小时额度"
    return f"{minutes:g}分钟额度"


def usage_lines(data, updated=None, error=None):
    lines = ["Codex 用量 · 60秒刷新"]
    if data is not None:
        buckets = data.get("rateLimitsByLimitId") or {"codex": data.get("rateLimits") or {}}
        for name, bucket in buckets.items():
            bucket = bucket or {}
            plan = bucket.get("planType") or "未知套餐"
            lines.append(f"{bucket.get('limitName') or name} · {plan}")
            found = False
            for key, fallback in (("primary", "主要额度"), ("secondary", "次要额度")):
                window = bucket.get(key)
                if not window:
                    continue
                found = True
                used = window.get("usedPercent")
                label = period(window.get("windowDurationMins"), fallback)
                if isinstance(used, (int, float)) and math.isfinite(used):
                    lines.append(f"{label}：剩余 {max(0, min(100, 100-used)):g}% · 已用 {used:g}%")
                else:
                    lines.append(f"{label}：暂无数据")
                reset = window.get("resetsAt")
                try:
                    reset_text = datetime.fromtimestamp(reset).strftime("%m-%d %H:%M")
                except (TypeError, ValueError, OSError, OverflowError):
                    reset_text = "未知"
                lines.append(f"  重置：{reset_text}")
            if not found:
                lines.append("暂无额度窗口数据")
            credits = bucket.get("credits") or {}
            if credits.get("unlimited"):
                lines.append("额外积分：无限")
            elif credits.get("hasCredits") and credits.get("balance") is not None:
                lines.append(f"额外积分：{credits['balance']}")
        if data.get("ordinaryUsageAllowed") is False:
            lines.append("当前普通额度不可用")
    if error:
        lines.append(error)
    elif data is None:
        lines.append("正在读取账号额度…")
    if updated:
        lines.append(f"更新：{updated:%H:%M:%S}" + ("（旧数据）" if error else ""))
    return lines


def clip(text, width):
    out, size = [], 0
    for char in str(text):
        if unicodedata.category(char).startswith("C"):
            continue
        cells = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in "WF" else 1)
        if size + cells > width:
            break
        out.append(char)
        size += cells
    return "".join(out)


def render(lines, once=False):
    if once:
        print("\n".join(lines), flush=True)
        return
    columns, rows = shutil.get_terminal_size((60, 12))
    # Keep the update/error indicator visible in short panes.
    if len(lines) > rows:
        lines = lines[:max(0, rows-1)] + [lines[-1]]
    frame = "\n".join(clip(line, max(1, columns-1)) for line in lines)
    sys.stdout.write("\033[H\033[2J" + frame)
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    client, data, updated, error = None, None, None, None
    next_read = 0
    try:
        while True:
            if not args.once:
                render(usage_lines(data, updated, error))
            if time.monotonic() >= next_read:
                try:
                    if client is None:
                        client = UsageClient(args.codex)
                        client.initialize()
                    data = client.call("account/rateLimits/read", {"excludeResetCreditDetails": True})
                    updated, error = datetime.now(), None
                except (OSError, RuntimeError, TimeoutError, ValueError, KeyError):
                    error = "额度读取失败，60秒后重试"
                    if client is not None:
                        client.close()
                        client = None
                next_read = time.monotonic() + 60
                render(usage_lines(data, updated, error), once=args.once)
                if args.once:
                    return 1 if error else 0
            time.sleep(1)
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
