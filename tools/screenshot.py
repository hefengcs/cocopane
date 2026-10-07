#!/usr/bin/env python3
"""Render a real, isolated tmux capture with synthetic data; requires Chrome."""
import html
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/images/dashboard.png"
COLS, ROWS = 176, 40
CELL, LINE = 9, 22

AGENT = r"""#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path
if 'app-server' in sys.argv:
    for line in sys.stdin:
        req = json.loads(line)
        if 'id' not in req:
            continue
        method = req['method']
        if method == 'initialize':
            result = {}
        elif method == 'config/read':
            result = {'config': {}}
        elif method == 'account/rateLimits/read':
            result = {'rateLimits': {'planType': 'demo', 'limitName': 'Codex (sample data)',
                'primary': {'usedPercent': 24, 'windowDurationMins': 300, 'resetsAt': 1791378000},
                'secondary': {'usedPercent': 38, 'windowDurationMins': 10080, 'resetsAt': 1791810000}}}
        else:
            raise RuntimeError(method)
        print(json.dumps({'id': req['id'], 'result': result}), flush=True)
else:
    log = Path.cwd() / 'training-demo.log'
    log.write_text('DEMO DATA - no training job is running\n'
        '[10:30:00] START image classifier\n'
        '[10:30:01] Dataset: 12,000 sample images\n'
        '[10:30:02] Device: cuda:0 | batch: 64\n'
        '[10:30:08] Epoch 01/20 | loss 1.284 | acc 58.2%\n'
        '[10:30:14] Epoch 02/20 | loss 0.936 | acc 67.5%\n'
        '[10:30:20] Epoch 03/20 | loss 0.714 | acc 74.8%\n'
        '[10:30:26] Epoch 04/20 | loss 0.582 | acc 79.3%\n')
    subprocess.run([os.environ['COCO_COMMAND'], 'set-log', str(log)], check=True, capture_output=True)
    print('''\033[H\033[2JCocoPane / agent conversation demo

  Synthetic conversation - no model request sent.

  > Run the image classifier and keep its progress visible.

  I will create a separate log for this task, bind it to
  the current dashboard, and record the result when it ends.

  $ coco set-log ./training-demo.log
  Log linked to slot 1.

  $ python -u train.py --epochs 20 --batch-size 64
      >> training-demo.log 2>&1

  Example progress
  ----------------------------------------------------
  Epoch          4 / 20
  Training loss  0.582
  Accuracy       79.3%

  The right side keeps account quota, GPU utilization
  and this task's output visible while you work here.

  > Summarize the result when training finishes.


  This pane uses a demo agent, not the Codex interface.
  The dashboard layout and monitor panes are real.
''', flush=True)
    time.sleep(300)
"""


def main():
    browser = next((shutil.which(name) for name in
                    ("google-chrome", "chromium", "chromium-browser") if shutil.which(name)), None)
    if not browser:
        raise SystemExit("Chrome/Chromium is required only for screenshot generation.")
    socket = "cocopane-screenshot-" + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix="cocopane-demo-") as directory:
        temp = Path(directory)
        binaries = temp / "bin"
        binaries.mkdir()
        (binaries / "python3").symlink_to(sys.executable)
        agent = binaries / "demo-agent"
        agent.write_text(AGENT)
        agent.chmod(0o755)
        gpu = binaries / "nvidia-smi"
        gpu.write_text("#!/bin/sh\nprintf '0, NVIDIA RTX 4090 (demo), 72, 8192, 24576, 61\\n'\n")
        gpu.chmod(0o755)
        home = temp / "home"
        home.mkdir()
        env = {"HOME": str(home), "PATH": f"{binaries}:/usr/bin:/bin", "LANG": "C.UTF-8",
               "TERM": "xterm-256color", "TZ": "UTC", "COLUMNS": str(COLS), "LINES": str(ROWS),
               "COCO_DATA_DIR": str(temp / "state"), "COCO_TMUX_SOCKET": socket,
               "CODEX_BIN": str(agent)}

        def tmux(*args, check=True):
            return subprocess.run(["tmux", "-L", socket, *args], env=env,
                                  check=check, capture_output=True, text=True, timeout=10).stdout

        try:
            subprocess.run([str(ROOT / "monitor/coco"), "open", "--detach"], cwd=temp,
                           env=env, check=True, capture_output=True, timeout=30)
            panes = []
            for _ in range(100):
                panes = []
                listing = tmux("list-panes", "-F", "#{pane_id} #{pane_left} #{pane_top} #{pane_width} #{pane_height}")
                for entry in listing.splitlines():
                    pane, x, y, w, h = entry.split()
                    content = tmux("capture-pane", "-p", "-t", pane)
                    panes.append((int(x), int(y), int(w), int(h), content))
                joined = "\n".join(p[4] for p in panes)
                if all(marker in joined for marker in ("Synthetic conversation", "sample data", "4090", "Epoch 04/20")):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Demo panes did not become ready")
            assert len(panes) == 4
            assert panes[1][2] == COLS * 40 // 100
        finally:
            tmux("kill-server", check=False)

        blocks = []
        capture_rows = max(y + height for _, y, _, height, _ in panes)
        for x, y, width, height, content in panes:
            lines = content.rstrip().splitlines()
            body = "<strong>" + html.escape(lines[0]) + "</strong>\n" + html.escape("\n".join(lines[1:]))
            blocks.append(f'<pre style="left:{x*CELL}px;top:{y*LINE}px;width:{width*CELL}px;'
                          f'height:{height*LINE}px">{body}</pre>')
        page = '''<!doctype html><meta charset="utf-8"><style>
        * {box-sizing:border-box} body {margin:0;background:#10151e;color:#dae2ef;padding:32px 40px;
        font-family:Arial,sans-serif} header {height:64px;display:flex;align-items:center;gap:16px}
        h1 {font-size:27px;margin:0;color:#f4f7fb;letter-spacing:-.5px}
        .tag {font-size:12px;color:#72dfc0;border:1px solid #306754;border-radius:4px;padding:6px 9px}
        .subtitle {margin-left:auto;font-size:14px;color:#8f9eb4}
        .terminal {position:relative;background:#263449;border:1px solid #32415a}
        pre {position:absolute;margin:0;background:#141c28;overflow:hidden;
        font:15px/22px "DejaVu Sans Mono","WenQuanYi Zen Hei",monospace;font-variant-ligatures:none}
        strong {color:#75dec3;font-weight:normal}
        footer {height:54px;display:flex;align-items:center;justify-content:space-between;
        font-size:13px;color:#94a4ba} .hint {color:#c7d2e3}
        </style><header><h1>CocoPane</h1><span class="tag">DEMO DATA</span>
        <span class="subtitle">AI coding agents · one terminal workspace</span></header>'''
        page += f'<div class="terminal" style="width:{COLS*CELL}px;height:{capture_rows*LINE}px">'
        page += "".join(blocks) + '</div><footer><span>Real tmux layout · synthetic conversation, quota, GPU &amp; logs</span>'
        page += '<span class="hint">Scroll: mouse wheel &nbsp; | &nbsp; Paste: Shift+Insert &nbsp; | &nbsp; Detach: Ctrl+b, d</span></footer>'
        source = temp / "screenshot.html"
        source.write_text(page)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([browser, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                        "--no-pdf-header-footer", f"--user-data-dir={temp / 'browser'}",
                        f"--window-size={COLS*CELL+80},{capture_rows*LINE+260}",
                        f"--screenshot={OUTPUT}", source.as_uri()], check=True, capture_output=True, timeout=30)
        print(OUTPUT)


if __name__ == "__main__":
    main()
