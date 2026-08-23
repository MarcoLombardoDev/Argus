# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
paths.py — Argus

Resolves the one directory every persistence path in the app is built from:
where should ``.env``, ``config/settings.json`` and ``data/`` live?

Running from source, "next to the code" and "the project root" are the same
place, so ``Path(__file__).resolve().parent.parent`` used to answer both
questions at once. They stop being the same place the moment the app is
frozen into a single executable with PyInstaller: a ``--onefile`` build
unpacks itself into a fresh temporary directory (``sys._MEIPASS``) on every
launch and deletes it on exit, and a module's ``__file__`` inside that bundle
resolves *into that temp directory*. Anything written there — settings, the
historical-price cache, saved AI sessions — would silently disappear the
moment the user closes the app.

``writable_base_dir()`` is the single place that tells the two cases apart,
so every module that persists data imports it instead of recomputing
``Path(__file__).resolve().parent.parent`` on its own.
"""

import sys
from pathlib import Path


def writable_base_dir() -> Path:
    """Directory where user data must persist across runs.

    - Frozen (PyInstaller): next to the executable itself, so a onefile
      build stays portable — copy the .exe anywhere and its data folder
      travels with it.
    - Running from source: the repository root, same as before.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
