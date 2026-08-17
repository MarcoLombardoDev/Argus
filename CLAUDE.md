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
the escape hatch for that: a manually-triggered (`workflow_dispatch` only, never on push)
job on a real `windows-latest` GitHub Actions runner, which is the only way to get a
genuine `.exe` without owning or renting a Windows machine. It also sidesteps the
CPU-vs-CUDA torch problem below, since a hosted runner has unrestricted internet access to
install the CPU wheel explicitly — some sandboxed dev environments do not.

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
  AGPL-3.0 §7 does not permit a licensee to impose. Do not reintroduce vectorbt, or an
  equivalent, without re-reading that clause: it would break the commercial offer.
- **Model weights are licensed separately from model code.** The `timesfm` package is
  Apache-2.0, but the TimesFM *checkpoints* pulled from Hugging Face carry their own
  terms. Verify the licence on the specific checkpoint before shipping it commercially.
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

## Commercial model — keep it aligned with the other two products

Argus is one of three dual-licensed products (**Iris**, **Argus**, **Proteus**) that
deliberately share **the same commercial offer**, differing only in price, scope wording
and the third-party review. Changing the shape of the offer here means changing it in all
three, or the alignment is lost.

The parts that must stay identical:

- **`COMMERCIAL-LICENSE.md`, same eleven sections**, same tier ladder: Community /
  Internal / OEM & Redistribution / Enterprise, plus a perpetual option on Internal or
  OEM scope.
- **Email is the only commercial channel.** GitHub Issues are for bugs and features.
- **Email support is included at every paid tier** (5 / 3 / 2 business days), never sold
  separately to a paying customer.
- **Custom development is never included**, at any tier, and is always quoted separately
  per project at a fixed price agreed before work starts.
- Perpetual fallback, no retroactive price rise, cancel any time, **no licence key and no
  phone-home**, 50% discount under 10 employees and €1M revenue, free licences for
  non-profits, academia and published research.

Argus's own prices:

| Tier | Price |
|---|---|
| Community (AGPL-3.0) | Free |
| Internal | €2,900 / year |
| OEM & Redistribution | €4,900 / year |
| Enterprise | from €14,000 / year |
| Perpetual (Internal / OEM scope) | €8,700 / from €14,900 one-off |
| Custom development, indicative | €1,200 / day |

The ladder is deliberately monotonic across the three products — Proteus < Iris < Argus on
every row. Move one price and check the other two still line up.

And the principle underneath all of it: **the free AGPL build is the whole product.** No
paid edition, no feature gate, no seat limit. A commercial licence buys *permission*, not
functionality. Never add a feature that is unlocked by paying.

## Dependency licence hygiene — now a commercial commitment

`COMMERCIAL-LICENSE.md` tells buyers that **no dependency imposes copyleft**. That
sentence has to stay true.

Before adding a dependency, check its licence. Permissive (MIT / BSD / Apache-2.0 / PSF /
HPND) is fine. Copyleft or "dual AGPL-or-pay" is not, because a commercial licence cannot
relicense someone else's code and the buyer would need a second licence.

This is not hypothetical here: the `vectorbt` dependency was removed for exactly this reason — see the note above and `COMMERCIAL-LICENSE.md` §9.

`tests/test_core.py::test_no_commons_clause_dependency_remains` enforces the vectorbt half
of this mechanically, failing if an import or a requirements line comes back. It is a
tripwire for one known offender, not a licence audit — a new dependency still needs a
human to read its licence.

PyInstaller is GPL-2.0 **with the bootloader exception**, which exists precisely to allow
proprietary frozen applications — that one is fine.

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

`CONTACT_EMAIL` in `core/version.py` is the single source of truth: the application footer,
the README and `COMMERCIAL-LICENSE.md` all quote it. The footer shows the address in full
and clicking it opens the mail client on a pre-filled enquiry — whoever is running the
software is exactly the person who might need a licence, and "available on request" tells
them nothing.
