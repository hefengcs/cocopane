#!/usr/bin/env python3
"""GPU pane with a readable fallback on CPU-only hosts."""
import shutil
import subprocess
import time

from _pane_codex_status import render


def snapshot():
    if not shutil.which("nvidia-smi"):
        return ["GPU", "No NVIDIA GPU / nvidia-smi detected.", "Agent and logs remain available."]
    try:
        result = subprocess.run([
            "nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4)
        if result.returncode:
            return ["GPU", "nvidia-smi unavailable; check the driver."]
        lines = ["GPU · utilization / memory / temperature"]
        for line in result.stdout.splitlines():
            fields = [part.strip() for part in line.split(",")]
            if len(fields) == 6:
                index, name, util, used, total, temperature = fields
                lines.append(f"{index}: {name}  {util}%  {used}/{total} MiB  {temperature}°C")
        return lines
    except (OSError, subprocess.TimeoutExpired):
        return ["GPU", "GPU query timed out; retrying…"]


if __name__ == "__main__":
    while True:
        render(snapshot())
        time.sleep(2)
