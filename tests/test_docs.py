#!/usr/bin/env python
# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.

"""Guards against the documentation drifting away from the product — and away
from the other three products it is deliberately kept in step with.

Orion, Iris, Proteus and Argus share a README skeleton on purpose, so a reader
who has found something in one knows where to look in the others. Nothing
enforces that at runtime, and a drifting document is invisible to anyone
editing the code — so it is checked here.

Argus no longer shares their commercial licence structure: it has none. The
tests below hold that line, because a withdrawn offer that survives in one
forgotten file is worse than no offer at all — and so is a README that stops
warning about the TimesFM weights. A screenshot referenced after being renamed
leaves a broken image on the project's front page; that is checked here too.
"""

from __future__ import annotations

import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP_NAME = "Argus"

#: The README section skeleton shared by the four products, in order. A section
#: renamed, dropped or reordered here has to be renamed, dropped or reordered in
#: all four, or this fails — which is the point.
README_SKELETON = (
    "Screenshots",
    "Table of Contents",
    f"What {APP_NAME} is",
    "Features",
    "Download",
    "Installation from source",
    "Usage",
    "How it works",
    "Requirements",
    "Development",
    "Testing",
    "Building a standalone executable",
    "Troubleshooting",
    "Scope and limitations",
    "Licence",
    "Contributing",
    "Disclaimer",
)

def read(name: str) -> str:
    with open(os.path.join(REPO, name), encoding="utf-8") as fh:
        return fh.read()


def headings(text: str, level: int) -> list[str]:
    """Every heading of exactly `level`, in order, outside code fences."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = re.match(rf"^#{{{level}}} (?!#)(.+)$", line)
        if match:
            found.append(match.group(1).strip())
    return found


# ---------------------------------------------------------------------------
# The shared skeleton
# ---------------------------------------------------------------------------

def test_the_readme_follows_the_shared_section_skeleton():
    """The four products' READMEs answer the same questions in the same order.
    A reader who knows where "Download" sits in one knows where it sits in all
    of them; a contributor who adds a section to one is told to add it to the
    rest.
    """
    assert tuple(headings(read("README.md"), 2)) == README_SKELETON


def test_every_internal_readme_link_points_at_a_heading_that_exists():
    """A table of contents is the first thing a reader clicks and the first
    thing a restructure breaks.
    """
    text = read("README.md")
    available = set()
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = re.match(r"^#{1,6} (.+)$", line)
        if not match:
            continue
        slug = match.group(1).strip().lower()
        slug = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", slug)
        slug = re.sub(r"[`*]", "", slug)
        slug = re.sub(r"[^\w\s-]", "", slug)
        available.add(re.sub(r"[ \t]", "-", slug.strip()))

    broken = sorted({t for t in re.findall(r"\]\(#([\w-]+)\)", text) if t not in available})
    assert not broken, f"README links to headings that do not exist: {broken}"


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

def test_every_referenced_image_exists():
    """A renamed capture must not leave a broken image in the README."""
    missing = [target for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", read("README.md"))
               if not target.startswith("http")
               and not os.path.exists(os.path.join(REPO, target))]
    assert not missing, f"README references missing images: {missing}"


# ---------------------------------------------------------------------------
# Licensing
#
# Argus is AGPL-3.0 and nothing else. The tests that used to police a price
# list, a tier ladder and a perpetual-option rule went with the commercial
# offer; what replaced them guards the one restriction that is real.
# ---------------------------------------------------------------------------

CONTACT = "marco.lombardo@gmail.com"


def test_no_commercial_offer_survives_anywhere():
    """The offer was withdrawn because it could not be kept: the forecast runs
    on weights licensed for non-commercial use only. A stray sentence still
    offering to sell a licence would be selling something that cannot be
    delivered.
    """
    for name in ("README.md", "CLA.md", "CONTRIBUTING.md", "THIRD-PARTY-LICENSES.md"):
        text = read(name)
        assert "COMMERCIAL-LICENSE.md" not in text, (
            f"{name} still points at a document that no longer exists")
    assert not os.path.exists(os.path.join(REPO, "COMMERCIAL-LICENSE.md"))


def test_the_weights_restriction_is_stated_where_a_user_meets_it():
    """The one thing a reader must not miss. Argus's own code is free; the
    TimesFM weights it downloads are licensed for testing, evaluation and
    research only, which excludes the trading this application exists to do.
    Burying that would be the most consequential omission in the project.
    """
    for name in ("README.md", "THIRD-PARTY-LICENSES.md"):
        lowered = read(name).lower()
        assert "non-commercial license" in lowered, (
            f"{name} does not name the licence the weights are under")
        assert "revenue" in lowered or "production" in lowered, (
            f"{name} does not say what the licence excludes")


def test_the_readme_says_argus_does_not_ship_the_weights():
    """It is the fact that keeps the AGPL distribution clean: the restricted
    artefact is fetched by the user, not redistributed by the project.
    """
    lowered = read("README.md").lower()
    assert "never ships the weights" in lowered or "not ship the weights" in lowered


def test_the_agpl_text_is_not_edited():
    """The AGPL may be applied to a work, never rewritten. Adding commercial
    terms to LICENSE itself would make the licence unrecognisable and
    unenforceable — and a reflowed copy is an edited copy: the licence's own
    header says changing it is not allowed, and GitHub stops recognising it.
    """
    licence = read("LICENSE")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in licence
    assert "Version 3, 19 November 2007" in licence
    assert "TERMS AND CONDITIONS" in licence

    # Deliberately not the word "price": the AGPL preamble uses it itself,
    # in "free as in freedom, not price". And matched on word boundaries,
    # because "VAT" is a substring of "private".
    for word in ("€", "VAT", "invoice", "per year", "subscription"):
        pattern = re.escape(word) if not word.isalpha() else rf"\b{word}\b"
        assert not re.search(pattern, licence, re.IGNORECASE), (
            f"LICENSE must stay verbatim AGPL, found {word!r}")


@pytest.mark.parametrize("document", ["README.md", "CLA.md"])
def test_a_reader_can_find_a_way_to_get_in_touch(document):
    """A project nobody can write to is harder to contribute to."""
    assert CONTACT in read(document)


def test_the_mail_subject_is_consistent():
    """The README opens a mail client. One enquiry arriving under two subjects
    looks like two enquiries, and the drift is invisible because nobody clicks
    every link.
    """
    subjects = set(re.findall(r"subject=[^)\s]+", read("README.md")))
    assert subjects == {f"subject={APP_NAME}"}, f"README uses {sorted(subjects)}"


def test_no_placeholder_survived_into_the_published_documents():
    """Regression: the contact address started life as a marked placeholder."""
    for name in ("README.md", "CLA.md"):
        lowered = read(name).lower()
        for placeholder in ("to be published", "tbd", "todo", "xxx", "your-domain"):
            assert placeholder not in lowered, f"{name}: placeholder left in: {placeholder!r}"


@pytest.mark.parametrize(
    "document", ["README.md", "CLA.md", "CONTRIBUTING.md",
                 "CHANGELOG.md", "LICENSE"])
def test_the_shared_document_set_is_present(document):
    """All four products carry the same six documents. One missing is one the
    others link to and this one does not have.
    """
    assert os.path.exists(os.path.join(REPO, document))


@pytest.mark.parametrize("document", ["CLA.md", "LICENSE"])
def test_licensing_documents_are_reachable_from_the_readme(document):
    assert document in read("README.md"), f"{document} is not linked from the README"


def test_the_inventory_document_is_reachable_from_the_licence():
    """A pointer to a file nobody links is a pointer to nothing."""
    assert "THIRD-PARTY-LICENSES.md" in read("README.md")
