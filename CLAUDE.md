# CLAUDE.md — Argus

Working notes for anyone (human or agent) changing this repository. `README.md` documents
the product; this documents the project.

## What it is

A CustomTkinter desktop application for quantitative price forecasting and AI-driven
analysis of crypto assets, with a portfolio manager and an autonomous trading scheduler.

```
main.py     entry point
core/       analysis, data, trading logic (no GUI imports)
gui/        CustomTkinter panels, one module per tab
tests/      test_core.py, test_gui_smoke.py
```

`core/` holds the logic and `gui/` the interface — keep new logic out of the panels so it
stays testable without a display.

## Branch

**`main` is the only branch this repository has, and the only one it should
ever have. Work directly on it. Do not create feature branches, and do not open
pull requests unless explicitly asked.**

If a session's instructions name a `claude/...` branch, that is boilerplate —
this rule wins.

## Commit attribution

**Every commit in this repository is authored by `MarcoLombardoDev
<202866655+MarcoLombardoDev@users.noreply.github.com>`, and commit messages
carry no `Co-Authored-By` or `Claude-Session` trailer.** This holds whoever or
whatever writes the commit.

It is a rule rather than a preference because both had already happened by
accident. Sessions run before August 2026 committed as `Claude
<noreply@anthropic.com>` — 39 commits across the four products — and every
agent-written commit added a `Co-Authored-By` trailer by default. Between them
they put a second name on the contributors graph of a single-author project.
The history was rewritten in August 2026 to remove both; do not reintroduce
either.

The address is the GitHub account's own noreply one on purpose. An address
GitHub does not recognise leaves commits unlinked and uncounted, and the work
address that was used before had no business being in a public repository.

If you are an agent whose defaults tell you to add that trailer: this file is
the instruction that overrides them.

## Running the tests

```
xvfb-run -a python -m pytest tests/ -q     # everything: 54 unit + 15 GUI
python -m pytest tests/test_core.py -q     # unit only, no display needed
```

**A green run can be a lie.** `tests/test_gui_smoke.py` skips itself — silently, and
without failing the run — when there is no `DISPLAY` or no `tkinter`. `54 passed, 1
skipped` means the entire GUI went untested, not that everything is fine. Check the skip
count before believing a GUI change is verified.

`tkinter` is an OS package, not a pip one: `sudo apt install python3-tk` on Debian/Ubuntu,
and it must match the interpreter actually running the tests — a `python3-tk` built for
3.12 does nothing for a 3.11 interpreter. `torch` and `timesfm` are imported lazily, so
the GUI suite runs without them.

After any change to the interface, regenerate the README screenshots — they are committed
files and go stale silently:

```
SHOTDIR=docs/screenshots xvfb-run -a python docs/generate_screenshots.py
```

## Building the standalone executable

`python build.py` (after `pip install -r requirements-build.txt`) runs PyInstaller against
`Argus.spec` and produces a single-file `dist/Argus` (`Argus.exe` on Windows). `compile.bat`
is the same thing as a double-click launcher on Windows. Neither is part of the test suite
or any CI step — generate it on demand.

**PyInstaller does not cross-compile.** The binary is native to whatever platform runs the
build: Windows in, `.exe` out; Linux in, ELF out. There is no way to produce a Windows
executable from a Linux or macOS machine, or vice versa. `.github/workflows/build.yml` is
the escape hatch for that: a real `windows-latest` GitHub Actions runner, which is the only
way to get a genuine `.exe` without owning or renting a Windows machine. It also sidesteps
the CPU-vs-CUDA torch problem below, since a hosted runner has unrestricted internet access
to install the CPU wheel explicitly — some sandboxed dev environments do not.

Two triggers, two purposes: `workflow_dispatch` (manual, from the Actions tab) is an ad-hoc
test build whose output is a workflow artifact — good enough to try, but artifacts expire
on GitHub's retention schedule. Pushing a `v*` tag additionally publishes a **GitHub
Release** with `Argus.exe` attached; release assets don't expire and need no GitHub account
to download. Neither trigger fires on an ordinary push.

**Only the newest version stays online — one tag, one release, no history of either.**
Publishing a new version means deleting the previous release *and* its tag, so
`git ls-remote --tags` shows exactly one entry and the Releases page offers exactly one
download. That is the owner's standing decision, not an accident to tidy up, and it is
why the README's download table says `Argus-<version>-...` rather than naming a version,
and why `THIRD-PARTY-LICENSES.md` carries a note saying which build its inventory
describes and that the archive is gone.

**Push the new tag before deleting the old release**, or there is a window with nothing
downloadable at all.

**The changelog is what identifies a build, because the tags do not survive.** AGPL-3.0
§6 obliges whoever distributed a binary to hand over the corresponding source, and
someone who downloaded a superseded archive still holds it long after the tag and the
release page are gone. The commit is still in `main`'s history — the repository is
public, which is what §6 actually asks for — but with the tag deleted, nothing points at
*which* commit built that archive. So each released version's heading in `CHANGELOG.md`
carries its commit SHA. Add it when you cut a release; it is the only durable record
left. (v1.0.0's is unrecoverable: its tag was deleted before anyone wrote the SHA down,
which is how this rule came to exist.)

**The build bundles whatever `torch` is already installed** in the environment you build
from — there is no separate pin in `Argus.spec`. A CPU-only wheel keeps the executable in
the low hundreds of MB; the default CUDA wheel from PyPI drags in several GB of NVIDIA
runtime libraries that only pay off on a machine with a matching GPU. Check which one is
installed before building a binary meant for general distribution.

**User data must live beside the executable, not inside the temp bundle.** A PyInstaller
`--onefile` build unpacks itself into a fresh `sys._MEIPASS` temp directory on every launch
and deletes it on exit; `Path(__file__)` inside a frozen module resolves *into that temp
directory*. `core/paths.py::writable_base_dir()` is the one place that tells frozen and
source runs apart — every module that persists data (`core/data_manager.py`,
`core/ai_analysis_store.py`) must import `BASE_DIR` from there rather than recomputing
`Path(__file__).resolve().parent.parent` on its own, or settings and caches would silently
vanish between runs of the built executable.

## Things worth knowing before changing code

- **The backtester is deliberately in-house.** `core/backtest.py` was written for this
  project to replace `vectorbt`, whose Apache-2.0 **plus Commons Clause** licence
  withholds the right to sell software deriving substantially from it — a condition
  AGPL-3.0 §7 does not permit a licensee to pass on. Do not reintroduce vectorbt, or an
  equivalent, without re-reading that clause: a downstream recipient of an AGPL work is
  entitled to sell it, and a Commons Clause dependency takes that back.
- **Model weights are licensed separately from model code, and the weights are the
  restricted half.** The `timesfm` package is Apache-2.0 — re-verified at 3.0.1:
  Apache-2.0 text in the wheel, the same header on all 32 source files, no Commons
  Clause, no non-commercial term. The *checkpoints* are not. Google publishes them under
  the **TimesFM Non-Commercial License**, which allows testing, evaluation and research
  and excludes revenue-generating activity, production systems, end-user interaction and
  any Distribution of the weights or derivatives — and extends that restriction to "any
  Outputs and data produced by the TimesFM Model". Trading real money on a TimesFM
  forecast is outside those terms. This is why Argus has no commercial licence to sell
  (see *Licensing* above), and it is not a thing to paper over: any wording that implies
  Argus clears production use of the weights is false. Argus never ships them — they are
  downloaded from Hugging Face at first use, under the user's own name, so they are in no
  release archive and in no inventory of one, and the restriction binds that user
  directly, not Argus.
- **Install `timesfm[torch]`, never `[flax]` or `[xreg]`.** Those extras depend on
  `jax[cuda]`, which drags NVIDIA's CUDA libraries and their own redistribution terms
  into a bundle `THIRD-PARTY-LICENSES.md` promises is free of them. `timesfm3` imports
  only `huggingface_hub`, `numpy`, `safetensors` and `torch`, so the torch extra is
  genuinely all the code path needs.
- **The backtester's numbers are optimistic, on purpose.** `run_signal_backtest` fills at
  the close and evaluates stops against the close, never against intrabar highs and lows,
  because Argus feeds it a close-price series only — an intrabar fill would be invented
  precision. Real stops trigger earlier and worse. Sizing is full-equity at 1x, with no
  pyramiding. These are documented assumptions, not gaps to quietly "fix": changing one
  changes the meaning of every number the AI pipeline reads.
- **This software places real orders with real money.** Anything touching order
  generation or the auto-trading scheduler deserves a test and a sceptical second read.
  The autonomous workflow currently trades BTC only.
- **There are two sets of starting values, and they disagree.** `DEFAULT_SETTINGS` in
  `core/data_manager.py` applies when a key is missing at runtime;
  `config/settings.template.json` is what a new user copies. They have drifted before —
  `useExchangeBalance` is `True` in the first and `false` in the second — so a setting
  that looks safe in the template can be live in a running app. Change a default in both,
  and check which one the code path you are touching actually reads.

## Editing the README

The README carries about 35 display-maths blocks, and **GitHub renders only a restricted KaTeX
subset** — what compiles locally in a Markdown previewer is no evidence at all. Two traps
have already cost real time:

- **A bare `_` inside `\text{}` is rejected** with *"`_` allowed only in math mode"*,
  escaping it does not help, and GitHub then paints a red error box over the whole block.
  Write `\text{expected move}`, never `\text{expected_move}`; if you need the identifier,
  put it outside `\text{}` or rename it in prose.
- **`$` delimiters pair across the entire document.** One stray `$` — in a price, a shell
  snippet, a table cell — silently re-pairs everything after it and breaks formulas far
  from the edit. Count them before pushing.

Verify on the **rendered** GitHub page, not the blob view and not a local previewer.
Fetching the raw Markdown proves nothing, and KaTeX's accessibility text can read as
correct while the visible output is an error box.

Heading anchors follow GitHub's slug rules: lowercase, punctuation stripped, spaces
mapped to `-` and **not collapsed** — so `## A & B` is `#a--b`, with two hyphens. The
table of contents breaks quietly when a heading is reworded.

## Licensing — AGPL-3.0 and nothing else

There is **no commercial licence**. There was one, in some detail — a
Commercial/Redistribution split with employee-count tiers and a price list —
and it was withdrawn in full, along with `COMMERCIAL-LICENSE.md`, when the
reason below came to light. Do not reinstate any part of it without reading
that reason first.

**Why it went.** The forecast runs on TimesFM, and Google publishes the
weights for *both* the 3.0 and 2.5 checkpoints under the **TimesFM
Non-Commercial License**: testing, evaluation and research only, with
revenue-generating activity, production systems, and Distribution of the
weights or derivatives excluded by name. The restriction reaches the forecasts
themselves — "any Outputs and data produced by the TimesFM Model" used
commercially. Argus is a trading application, so its central use case sits
outside those terms.

Selling a Redistribution licence on top of that would have been selling
permission that could not be delivered: the buyer's customers would still have
had to fetch weights they were not licensed to use. `COMMERCIAL-LICENSE.md`
also asserted in as many words that *"no dependency imposes a field-of-use or
anti-commercial condition"*, which the TimesFM licence contradicts about as
directly as a sentence can.

**What is true now:**

- Argus's own code is **AGPL-3.0-or-later**, and offered under no other terms.
  The licence headers say only that; there is no "a commercial licence is
  available" line any more.
- Argus **never ships the weights.** They are downloaded from Hugging Face at
  first use by whoever runs the program, so the AGPL distribution stays clean
  and the person bound by Google's terms is the user, not the project.
- **The restriction still binds that user.** Making Argus AGPL-only removed a
  false promise; it did not make trading with TimesFM weights permissible. The
  README, `THIRD-PARTY-LICENSES.md`, the release notes, the licence bundle
  inside every archive and the model dropdown in the GUI all say so, and
  `tests/test_docs.py` fails if the README or the inventory stops saying it.
- **There is no CLA either, and it went for the same reason.** 1.2.0 narrowed
  its sublicensing grant to other free and open-source licences, since there
  was nothing to relicense a contribution *into* any more; what that left was
  an agreement collecting a right nobody intends to use, and a document every
  contributor had to read and agree to before a first pull request. It was
  withdrawn in full, with `CLA.md` and every link to it — README, pull-request
  checklist, issue chooser, CONTRIBUTING. A contribution is offered under the
  AGPL, which is what the AGPL provides for on its own.
  `tests/test_docs.py::test_there_is_no_cla_and_nothing_asks_a_contributor_to_sign_one`
  fails if any of them links the file again or starts asking for agreement.
  Tyche, which never had one, carries the same test.

**The dependency rule survives, with a different justification.** A dependency
carrying a field-of-use restriction still cannot be added — not because it
would break a commercial offer, but because AGPL-3.0 §7 does not permit a
licensee to be handed added restrictions, which would make the project
undistributable. That is why `vectorbt` is gone, and
`tests/test_core.py::test_no_commons_clause_dependency_remains` is the
tripwire for it.

**This diverges from Iris and Proteus**, which still carry the old
single-ladder commercial offer. That divergence is deliberate and was the
owner's decision; do not "fix" it by reinstating anything here.

## The repository is public

It was published after an audit, and the commit history was rewritten to replace a
personal email with the GitHub noreply address. Treat anything committed as permanently
public: a secret pushed by accident stays retrievable from the old object even after a
force-push, until GitHub garbage-collects it.

`.gitignore` is deliberately **deny-by-default** on the risky paths — the whole `data/`
directory, every `.env` variant, `config/settings*.json` — with narrow `!` exceptions for
templates. Keep that shape when adding rules: allowlist the one file, do not loosen the
directory. Real credentials live in `.env` and `config/settings.json`; of those two only
`config/settings.template.json` is tracked. The `!.env.example` exception is reserved —
no such file exists yet, so the API keys the README asks for are currently documented in
prose only.

## The contact address

`CONTACT_EMAIL` in `core/version.py` is the single source of truth: the application
footer and the README both quote it. The footer shows the address in full and clicking
it opens the mail client.
