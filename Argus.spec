# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

# Argus.spec — PyInstaller build specification
#
# Produces a single, self-contained executable: `python build.py` (or
# `pyinstaller Argus.spec --noconfirm --clean` directly) is the on-demand way
# to generate it — nothing here runs automatically as part of testing or CI.
#
# The executable is native to whatever platform builds it: run this on
# Windows for a .exe, on Linux for an ELF binary, on macOS for a Mach-O
# binary. PyInstaller does not cross-compile.
#
# User data (`.env`, `config/settings.json`, `data/`) is written next to the
# built executable, not inside it — see core/paths.py. Copy the executable
# anywhere and a fresh, empty data folder is created beside it on first run.
#
# Torch is the dependency that decides how big this gets. A CPU-only torch
# install (`pip install torch --index-url https://download.pytorch.org/whl/cpu`
# in the venv you build from) keeps the binary in the few-hundred-MB range and
# runs anywhere. Whatever torch build is installed when you run this spec is
# the one that gets bundled — if it's a CUDA build, its (large) CUDA runtime
# libraries are pulled in too, useful only on a machine with a matching GPU.

import sys

from PyInstaller.utils.hooks import collect_data_files

# customtkinter ships its themes and fonts as package data (JSON + TTF under
# customtkinter/assets/); without this the built app starts but every widget
# renders with the wrong theme or falls back to a system font.
datas = collect_data_files("customtkinter")
# Both files: Windows takes the .ico through iconbitmap, and Tk
# everywhere else needs the PNG, which iconphoto reads. The .icns is not in
# here — it is an executable resource, not something read at run time.
datas += [("assets/app_icon.ico", "assets"), ("assets/app_icon.png", "assets")]

# The executable's own icon, per platform, because PyInstaller will not
# convert between the formats on its own: `normalize_icon_type` accepts only
# .ico on Windows and only .icns on macOS, converting anything else *if Pillow
# happens to be installed*. A hardcoded .ico is what killed XIP's first macOS
# release. None on Linux, where PyInstaller ignores an icon and warns about it
# on every build.
#
# **The macOS build has no icon, and this does not give it one.** EXE embeds an
# icon only on Windows — the darwin branch of its assembly step converts the
# architecture and nothing else. On macOS the icon belongs to `BUNDLE()`, which
# Argus deliberately does not have: core/paths.py writes .env, config/ and
# data/ beside sys.executable, which inside an .app would be inside the app
# bundle. So the value below is correct rather than effective, and it is here
# so that nobody wires the .ico back in expecting a different outcome.
_ICON_FOR_EXE = {
    "win32": "assets/app_icon.ico",
    "darwin": "assets/app_icon.icns",
}.get(sys.platform)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # readline is excluded for a licensing reason, not for size. PyInstaller
    # collects the standard library's optional readline extension, which links
    # libreadline — GPL-3.0-or-later, with no linking exception — so a GPL-3
    # library ended up inside an archive distributed under AGPL-3.0, whose
    # section 7 does not permit added restrictions. libpython does not link
    # it; only this module does, and Argus is a windowed application that
    # never reads a line from an interactive prompt. rlcompleter goes with it:
    # it imports readline and exists for nothing else.
    excludes=["readline", "rlcompleter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Argus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # windowed app: no terminal window behind the GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON_FOR_EXE,
)
