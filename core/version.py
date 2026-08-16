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

# Commercial licensing, quotes, OEM and enterprise enquiries. Email is the
# only commercial channel — see COMMERCIAL-LICENSE.md.
CONTACT_EMAIL = "marco.lombardo@gmail.com"
