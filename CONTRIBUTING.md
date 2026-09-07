# Contributing to Argus

Thanks for wanting to help. This file describes how the project works so a patch has a
good chance of being merged quickly.

## Ground rules

Argus **places real orders with real money** when it is configured to. Two rules
follow from that and are not negotiable:

- **Paper trading stays the safe default in the shipped template.** A change that makes it
  easier to reach the exchange by accident will not be merged.
- **Never commit API keys, secrets, account identifiers, real balances or real positions.**
  `.env` and `config/settings.json` stay out of the repository, and fixtures use synthetic
  data.

A dependency carrying a field-of-use or anti-commercial condition — the Commons Clause, for
one — cannot be added: AGPL-3.0 §7 does not let a licensee pass such a condition on, so it
would make the project undistributable. That one already cost this project a rewrite of the
backtester.

## There is no CLA

Argus is **AGPL-3.0-or-later and nothing else**, so there is no Contributor License
Agreement and no copyright assignment. Nobody signs anything.

That follows from the licensing rather than being a separate decision. A CLA exists so one
party can license the whole work on terms other than the ones contributors chose — which is
what a commercial tier needs. Argus had such a tier and **withdrew it in 1.2.0**: the
forecast runs on TimesFM weights licensed for non-commercial use only, so the offer could
not be kept. With nothing to relicense into, a CLA would be collecting a right nobody
intends to use.

You keep the copyright in your work. You offer it under the AGPL, like everything else
here, which is what the AGPL provides for on its own.

## Getting set up

```bash
git clone https://github.com/MarcoLombardoDev/Argus.git
cd Argus
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt
cp config/settings.template.json config/settings.json
python -m pytest tests/test_core.py -q
```

The GUI smoke tests need a display; on a headless machine:

```bash
xvfb-run -a python -m pytest tests/ -q
```

The whole suite is **offline** — it never contacts an exchange, a data provider or an LLM —
so it is safe to run with or without API keys configured.

## Before you write code

Read the *How it works* section of the README first — particularly
*Architecture overview* and *Project structure*. Three rules carry most of the design:

1. **Secrets never touch `config/settings.json`.** `.env` is the only store, and the JSON
   is redacted on save.
2. **Every long operation runs on a worker thread** and reports back through a queue. No
   network call and no model inference happens on the Tk thread.
3. **An AI decision is constrained by the backtest, not trusted on its own.** A change that
   lets a qualitative verdict size a position unchecked is a change to the product, not a
   patch — open an issue first.

One more, easy to get wrong: **bump the version only in `core/version.py`.** A frozen
executable has no source tree to derive one from.

## Style

- `ruff check .` must be clean. The rules are in `ruff.toml`, and they are the ones
  the sibling products use. Three are switched off there rather than worked around,
  each with the reason beside it: this codebase writes long lines and one-line `if`
  bodies on purpose, and rewrapping somebody else's style is not a defect being
  fixed. Everything else applies, to every file.
- Comments explain *why*, not *what*. If a line encodes a non-obvious fact about an
  exchange's API, a CCXT quirk or a model's output format, say so — the next person will
  not rediscover it.
- User-facing strings are sentences, not error codes. A value that is unavailable is
  `N/A`, never a crash: formatters and export paths are tested against those sentinels.

## Tests

New behaviour needs a test, and every bug fix arrives with a test that fails
without the fix.

- **The suite is offline and must stay offline.** It never contacts an exchange, a data
  provider or an LLM.
- Two things the suite deliberately guards, because they only ever surfaced at runtime:
  formatting against real-world data (values reloaded from CSV arrive as strings, and AI
  results carry `"N/A"` and `"DISABLED"` sentinels), and deferred callbacks (an exception
  inside a queued callback surfaces long after the code that scheduled it).

## Commits and pull requests

- One logical change per commit; a message that says what changed and why.
- Describe the user-visible effect in the pull request, and say how you tested it.
- Add an entry to `CHANGELOG.md` under *Unreleased*.
- If you changed anything documented in the README, update it in the same pull request.

## Reporting bugs

Include your operating system, your Python version, what you did, what you
expected and what happened. `data/` holds the caches and the run history — attach the
relevant file, **after checking it carries no account identifiers, balances or keys**. For
an exchange problem, name the exchange and whether you were in paper or live mode.
