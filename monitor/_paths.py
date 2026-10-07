"""User-owned state, independent of the source/install directory."""
import os
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent


def state_dir():
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return Path(os.environ.get("COCO_DATA_DIR") or base / "cocopane").expanduser().absolute()


def log_dir():
    return Path(os.environ.get("COCO_LOG_DIR") or state_dir() / "logs").expanduser().absolute()


def socket_name():
    # Separate from the original private installation and the default tmux server.
    return os.environ.get("COCO_TMUX_SOCKET", "coco-public")


def latest_path(slot):
    return log_dir() / ("latest.log" if str(slot) == "1" else f"latest{slot}.log")
