"""Nuitka build script for MOPS."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DIST_DIR = REPO_ROOT / "dist"


def build():
    DIST_DIR.mkdir(exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--output-dir=" + str(DIST_DIR),
        "--output-filename=mops",
        "--include-package=mops",
        "--nofollow-import-to=tests",
        str(REPO_ROOT / "mops" / "__main__.py"),
    ]

    # Windows-specific options
    if sys.platform == "win32":
        cmd.append("--windows-disable-console")

    print(f"Building: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    exe = DIST_DIR / ("mops.exe" if sys.platform == "win32" else "mops")
    print(f"Build complete: {exe}")


if __name__ == "__main__":
    build()
