# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
build.py — Argus

Generates the single-file Argus executable on demand. Not part of the test
suite or any CI step — run it explicitly when you want a distributable
binary:

    python build.py

Produces dist/Argus(.exe) on the platform you run it on: PyInstaller does
not cross-compile, so build on Windows for a .exe, on Linux for an ELF
binary, on macOS for a Mach-O binary. See Argus.spec for what gets bundled
and why, including the CPU-vs-CUDA torch size trade-off.

Requires PyInstaller, which is a build-time tool only — it is intentionally
not in requirements.txt, since running Argus from source never needs it:

    pip install -r requirements-build.txt
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SPEC_FILE = REPO_ROOT / "Argus.spec"


def main() -> int:
    if importlib.util.find_spec("PyInstaller") is None:
        print("[build] PyInstaller not found — installing it now "
              "(pip install -r requirements-build.txt)...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements-build.txt"],
            cwd=REPO_ROOT, check=True,
        )

    print(f"[build] Running PyInstaller against {SPEC_FILE.name} ...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm", "--clean"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print("[build] PyInstaller failed — see output above.")
        return result.returncode

    dist_dir = REPO_ROOT / "dist"
    candidates = [p for p in dist_dir.glob("Argus*") if p.is_file()]
    if not candidates:
        print(f"[build] PyInstaller reported success but no binary was found in {dist_dir}.")
        return 1

    binary = candidates[0]
    size_mb = binary.stat().st_size / (1024 * 1024)
    print(f"[build] Done: {binary}  ({size_mb:.0f} MB)")
    print("[build] Copy it anywhere — it creates its own data/ and config/ next to itself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
