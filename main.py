"""
main.py — Argus
Application entry point. Launches the main window.
"""

import argparse
import sys
import os

# Add the project root to the PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.version import APP_NAME, APP_TITLE, __version__


def _parse_args():
    """Handle ``--version`` / ``--help`` and return an exit code, or None.

    Argus is a GUI application, but the release workflow smoke-tests every
    bundle it builds by running it with ``--version``: a binary that cannot
    even report its own version is a broken binary, and that has to be caught
    before the asset is offered for download rather than after. Parsed before
    ``gui.app`` is imported, so the check costs a fraction of a second and
    needs no display — importing the GUI pulls in torch and CCXT.
    """
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=APP_TITLE,
        epilog="Run without arguments to open the interface.",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="store_true",
        help="print the version and exit",
    )
    args, unknown = parser.parse_known_args()
    if unknown:
        parser.error(f"unrecognised arguments: {' '.join(unknown)}")
    if args.version:
        # Deliberately not argparse's own "version" action: that one writes to
        # sys.stdout unconditionally, and a windowed PyInstaller build on
        # Windows may not have one. print() is a no-op when sys.stdout is
        # None, so the exit code stays 0 either way — which is what the
        # workflow's smoke test actually checks.
        print(f"{APP_NAME} {__version__}")
        return 0
    return None


def main():
    exit_code = _parse_args()
    if exit_code is not None:
        return exit_code

    from gui.app import ArgusApp

    app = ArgusApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
