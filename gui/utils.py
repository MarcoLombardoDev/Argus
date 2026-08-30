# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

import contextlib
import types
from tkinter import ttk

import customtkinter as ctk

# Shared ttk scrollbar style name. ttk.Scrollbar is a native widget and is NOT
# themed by CustomTkinter, so without this it renders light grey against the
# dark panels.
SCROLLBAR_STYLE_V = "Argus.Vertical.TScrollbar"
SCROLLBAR_STYLE_H = "Argus.Horizontal.TScrollbar"

_SB_TROUGH = "#181a20"
_SB_THUMB = "#474d57"
_SB_THUMB_ACTIVE = "#5d6673"


def setup_scrollbar_style():
    """Registers the dark ttk scrollbar styles. Idempotent."""
    style = ttk.Style()
    with contextlib.suppress(Exception):
        style.theme_use("clam")
    for name, orient in ((SCROLLBAR_STYLE_V, "vertical"), (SCROLLBAR_STYLE_H, "horizontal")):
        opts = dict(  # noqa: C408 - reads as a keyword table, not a literal
            troughcolor=_SB_TROUGH,
            background=_SB_THUMB,
            bordercolor=_SB_TROUGH,
            arrowcolor="#848e9c",
            darkcolor=_SB_TROUGH,
            lightcolor=_SB_TROUGH,
            relief="flat",
            borderwidth=0,
        )
        if orient == "vertical":
            # `width` is only meaningful on the vertical scrollbar, and passing
            # None to style.configure raises TclError.
            opts["width"] = 12
        style.configure(name, **opts)
        style.map(
            name,
            background=[("active", _SB_THUMB_ACTIVE), ("pressed", _SB_THUMB_ACTIVE)],
            arrowcolor=[("active", "#eaecef")],
        )


def dark_scrollbar(parent, orient: str, command) -> ttk.Scrollbar:
    """Creates a ttk.Scrollbar using the shared dark style."""
    setup_scrollbar_style()
    style_name = SCROLLBAR_STYLE_V if orient == "vertical" else SCROLLBAR_STYLE_H
    return ttk.Scrollbar(parent, orient=orient, command=command, style=style_name)


def apply_binance_tab_style(segmented_button: ctk.CTkSegmentedButton):
    """
    Patches a CTkSegmentedButton to ensure that selected tabs/segments
    have dark text (#181a20) and unselected ones have white text.
    """
    orig_select = segmented_button._select_button_by_value
    orig_unselect = segmented_button._unselect_button_by_value

    def new_select(self, value):
        orig_select(value)
        if value in self._buttons_dict:
            self._buttons_dict[value].configure(text_color="#181a20")

    def new_unselect(self, value):
        orig_unselect(value)
        if value in self._buttons_dict:
            self._buttons_dict[value].configure(text_color="white")

    segmented_button._select_button_by_value = types.MethodType(new_select, segmented_button)
    segmented_button._unselect_button_by_value = types.MethodType(new_unselect, segmented_button)

    # Immediately apply style to current buttons
    for val, btn in segmented_button._buttons_dict.items():
        if val == segmented_button._current_value:
            btn.configure(text_color="#181a20")
        else:
            btn.configure(text_color="white")
