#!/usr/bin/env python3
"""Build an explicit-source archive; never bundle user state or account files."""
from pathlib import Path
import hashlib
import tarfile


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("README.md", "README.zh-CN.md", "LICENSE", "VERSION", ".gitignore",
              "install.py", "install.sh", "CONTRIBUTING.md", "CHANGELOG.md")


def package():
    version = (ROOT / "VERSION").read_text().strip()
    name = "cocopane-" + version
    files = [ROOT / file for file in ROOT_FILES]
    files.append(ROOT / "docs/images/dashboard.png")
    for directory in ("monitor", "tests", "tools", "ci"):
        for file in (ROOT / directory).rglob("*"):
            if not file.is_file() or file.is_symlink() or "__pycache__" in file.parts:
                continue
            if file.suffix in (".py", ".sh", ".md", ".conf", ".yml") or file.name == "coco":
                files.append(file)
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / (name + ".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        for file in sorted(files):
            info = tar.gettarinfo(str(file), arcname=name + "/" + str(file.relative_to(ROOT)))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with file.open("rb") as stream:
                tar.addfile(info, stream)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(digest + "  " + archive.name + "\n")
    print(archive)
    print(digest)
    return archive


if __name__ == "__main__":
    package()
