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

## Things worth knowing before changing code

- **The backtester is deliberately in-house.** `core/backtest.py` was written for this
  project to replace `vectorbt`, whose Apache-2.0 **plus Commons Clause** licence
  withholds the right to sell software deriving substantially from it — a condition
  AGPL-3.0 §7 does not permit a licensee to impose. Do not reintroduce vectorbt, or an
  equivalent, without re-reading that clause: it would break the commercial offer.
- **Model weights are licensed separately from model code.** The `timesfm` package is
  Apache-2.0, but the TimesFM *checkpoints* pulled from Hugging Face carry their own
  terms. Verify the licence on the specific checkpoint before shipping it commercially.
- **This software places real orders with real money.** Anything touching order
  generation or the auto-trading scheduler deserves a test and a sceptical second read.
  The autonomous workflow currently trades BTC only.

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

PyInstaller is GPL-2.0 **with the bootloader exception**, which exists precisely to allow
proprietary frozen applications — that one is fine.

## The contact address

`CONTACT_EMAIL` in `core/version.py` is the single source of truth: the application footer,
the README and `COMMERCIAL-LICENSE.md` all quote it. The footer shows the address in full
and clicking it opens the mail client on a pre-filled enquiry — whoever is running the
software is exactly the person who might need a licence, and "available on request" tells
them nothing.
