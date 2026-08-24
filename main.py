# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

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
    """Handle ``--version``, ``--self-check`` and ``--help``.

    Returns an exit code when one of them was asked for, or None to carry on
    and open the window.

    Argus is a GUI application, but the release workflow runs every bundle it
    builds before offering it for download. ``--version`` is the cheap half of
    that — a binary that cannot report its own version is broken — and
    ``--self-check`` is the half that means something: it starts Tk and writes
    both export formats, which is where a frozen bundle actually breaks.

    Both are handled here rather than after ``gui.app`` is imported, so
    ``--version`` costs a fraction of a second: importing the GUI pulls in
    torch and CCXT. ``--self-check`` pays that cost deliberately, since torch
    loading is one of the things it exists to prove.
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
    parser.add_argument(
        "--self-check",
        action="store_true",
        help=(
            "check a built bundle can start Tk and run a backtest and write both export formats, then exit"
        ),
    )
    parser.add_argument(
        "--self-check-report",
        metavar="FILE",
        help="also write the self-check report here; a --windowed build has "
             "no stdout to read it from",
    )
    args, unknown = parser.parse_known_args()
    if unknown:
        parser.error(f"unrecognised arguments: {' '.join(unknown)}")
    if args.self_check:
        from core import selfcheck

        return selfcheck.run(args.self_check_report)
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
