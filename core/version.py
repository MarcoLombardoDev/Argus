# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""
version.py — Argus

Single source of truth for the application's identity and its commercial
contact address.

CONTACT_EMAIL lives here rather than being spelled out at each call site so
that changing it — moving from a personal address to a role address on an
owned domain, say — is a one-line edit in the code, not a hunt through the
GUI. The Markdown documents carry their own copies by necessity; the code
does not have to.
"""

APP_NAME = "Argus"
APP_TITLE = "Argus — Advanced Market Forecast & AI Analysis"

# Shown in the window title. Bump by hand on a release; a frozen executable
# has no .py sources on disk to derive a date from (see gui/app.py, which
# used to walk the source tree for this and would have printed 1970.01.01
# out of a PyInstaller bundle).
__version__ = "1.0.0"

# Commercial licensing, quotes, OEM and enterprise enquiries. Email is the
# only commercial channel — see COMMERCIAL-LICENSE.md.
CONTACT_EMAIL = "marco.lombardo@gmail.com"
