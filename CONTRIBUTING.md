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
one — cannot be added: it would break the commercial licence. That one already cost this
project a rewrite of the backtester.

## The Contributor License Agreement

Argus is dual-licensed: AGPL-3.0 for everyone, and commercial terms for those who cannot
accept the AGPL's obligations. That is only possible if one party can license the whole
work both ways, so **every contributor must agree to the
[Contributor License Agreement](CLA.md)** before a pull request can be merged.

> **To agree:** include
> `I have read and agree to the Contributor License Agreement (CLA.md).`
> in your pull request description. Your first pull request constitutes your agreement.

You keep the copyright in your work, and you receive a perpetual, royalty-free commercial
licence to Argus for your own use — see
[COMMERCIAL-LICENSE.md §12](COMMERCIAL-LICENSE.md#12-contributors).

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

- `python -m pyflakes core/ gui/ main.py` must be clean.
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
