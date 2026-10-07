#!/usr/bin/env python3
"""Install only coco's files; never modify shell startup files or agent settings."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
MARKER = ".cocopane-install.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    parser.add_argument("--uninstall", action="store_true", help="Remove this installation; keep logs and running sessions")
    args = parser.parse_args()
    if sys.version_info < (3, 9):
        parser.error("Python 3.9+ required")
    prefix = args.prefix.expanduser().resolve()
    target = prefix / "share/cocopane"
    command = prefix / "bin/coco"
    if args.uninstall:
        marker = target / MARKER
        if target.is_symlink() or not marker.is_file():
            parser.error("No owned coco installation at this prefix; refusing to remove it")
        data = json.loads(marker.read_text())
        if data.get("package") != "cocopane" or data.get("prefix") != str(prefix):
            parser.error("Installation marker mismatch; refusing to remove it")
        if command.is_symlink() and command.resolve() == target / "monitor/coco":
            command.unlink()
        elif command.exists() or command.is_symlink():
            parser.error("bin/coco was replaced by another command; refusing to remove it")
        shutil.rmtree(target)
        print("Uninstalled coco. Logs, CLI accounts and running sessions were kept.")
        return 0
    if target.exists() or target.is_symlink() or command.exists() or command.is_symlink():
        parser.error("Installation path or bin/coco already exists. Choose another --prefix; existing files were not changed.")
    target.parent.mkdir(parents=True, exist_ok=True)
    command.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".coco-install-", dir=target.parent))
    moved = False
    try:
        # Explicit export list: no logs, credentials, personal notes or bytecode.
        for name in ("VERSION", "LICENSE", "README.md", "README.zh-CN.md", "install.py", "install.sh"):
            shutil.copy2(ROOT / name, staging / name)
        (staging / "docs/images").mkdir(parents=True)
        shutil.copy2(ROOT / "docs/images/dashboard.png", staging / "docs/images/dashboard.png")
        (staging / "monitor").mkdir()
        for file in (ROOT / "monitor").iterdir():
            if file.is_file() and not file.name.startswith("test_") and file.suffix in (".py", ".sh", ".md", ".conf", ""):
                shutil.copy2(file, staging / "monitor" / file.name)
        (staging / MARKER).write_text(json.dumps({"package": "cocopane", "prefix": str(prefix)}))
        (staging / "monitor/coco").chmod(0o755)
        os.rename(staging, target)
        moved = True
        command.symlink_to(target / "monitor/coco")
    except Exception:
        shutil.rmtree(target if moved else staging, ignore_errors=True)
        raise
    print(f"Installed: {command}\nNext: {command} doctor")
    if str(command.parent) not in os.environ.get("PATH", "").split(os.pathsep):
        import shlex
        print("Add to your shell PATH if desired: export PATH=" + shlex.quote(str(command.parent)) + ':"$PATH"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
