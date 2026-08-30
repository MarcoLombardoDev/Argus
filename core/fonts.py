# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""The interface font, resolved once for the whole application."""

#: Interface font, in order of preference. The same list in all four products.
#:
#: Segoe UI first because it is what Windows uses for its own interface, and
#: three of these four were already getting it there -- two by asking for it,
#: one because Tk and Qt both default to it. The rest are the equivalent on
#: the other platforms, so nothing has to fall back to a font chosen by
#: whichever toolkit happened to be asked.
#:
#: Arial is deliberately not on this list. It was hard-coded in a handful of
#: places here, which is what made the small labels the odd ones out.
UI_FONT_PREFERENCE = (
    "Segoe UI",          # Windows
    "SF Pro Text",       # macOS 11+
    "Helvetica Neue",    # older macOS
    "Noto Sans",         # most Linux desktops
    "DejaVu Sans",       # the rest
)

_UI_FONT_FAMILY: str | None = None


def ui_font_family() -> str:
    """The first font in UI_FONT_PREFERENCE this machine actually has.

    Resolved once and remembered: ``families()`` walks the whole font
    database, and this is asked for on every label built.

    Falls back to whatever Tk itself would have used, which is the right
    answer for a machine that has none of these -- better a font the system
    chose than a name it will silently substitute.
    """
    global _UI_FONT_FAMILY
    if _UI_FONT_FAMILY is not None:
        return _UI_FONT_FAMILY

    try:
        from tkinter import font as tkfont

        available = {name.lower() for name in tkfont.families()}
        for family in UI_FONT_PREFERENCE:
            if family.lower() in available:
                _UI_FONT_FAMILY = family
                return family
        _UI_FONT_FAMILY = str(tkfont.nametofont("TkDefaultFont").actual("family"))
    except Exception:  # noqa: BLE001 - a font is never worth failing to start
        _UI_FONT_FAMILY = "TkDefaultFont"
    return _UI_FONT_FAMILY


def ui_font(size: int, *styles: str) -> tuple:
    """A Tk font spec in the interface font: ``ui_font(9, "bold")``."""
    return (ui_font_family(), size, *styles)
