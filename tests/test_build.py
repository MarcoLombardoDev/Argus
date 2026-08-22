"""
tests/test_build.py — Argus

Regression tests for .github/workflows/build.yml's release-publishing step.
These don't run the workflow itself (that only happens on GitHub's own
Windows runners); they parse the checked-in YAML so a future edit can't
silently reintroduce either bug already hit in production:

- `gh release create --generate-notes` dumps every commit since the last
  release into the notes field — for a first release, the entire project
  history — which is not a description of what's being downloaded.
- the fallback path (`gh release upload`, taken whenever a release already
  exists for the tag — which happens whenever the tag was made through
  GitHub's own "Draft a new release" UI) left that release's title/notes
  untouched, so a wrong or empty title from the UI stuck around even after
  a successful run.
"""
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "build.yml"


def _release_step_text() -> str:
    text = WORKFLOW_PATH.read_text()
    start = text.index("- name: Publish GitHub Release")
    rest = text[start:]
    next_step = rest.find("\n      - name:", 1)
    return rest if next_step == -1 else rest[:next_step]


def test_release_notes_are_fixed_not_generated():
    step = _release_step_text()
    assert "--generate-notes" not in step, (
        "auto-generated notes list every commit since the last release — "
        "unreadable for a first release. Use a fixed --notes string instead."
    )
    assert "--notes" in step


def test_release_title_and_notes_are_corrected_even_on_the_fallback_path():
    step = _release_step_text()
    lines = [line.strip() for line in step.splitlines() if line.strip()]
    edit_lines = [line for line in lines if line.startswith("gh release edit")]
    assert edit_lines, "expected an unconditional 'gh release edit' line"
    assert "--title" in edit_lines[0]
    assert "--notes" in edit_lines[0]
    assert "--draft=false" in edit_lines[0]
