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

from PyInstaller.utils.hooks import collect_data_files

# customtkinter ships its themes and fonts as package data (JSON + TTF under
# customtkinter/assets/); without this the built app starts but every widget
# renders with the wrong theme or falls back to a system font.
datas = collect_data_files("customtkinter")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    # icon="assets/app_icon.ico",  # uncomment once an icon file exists
)
