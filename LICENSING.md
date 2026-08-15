# Argus — Licensing & Commercial Terms

> **This document is a commercial summary, not a contract.** The binding terms are
> those of the signed licence agreement. Nothing here is legal advice, and the
> price list below is indicative — see [Getting a Quote](#8-getting-a-quote).

---

## 1. The short version

| You are... | Licence you need | Cost |
|---|---|---|
| An individual trading your own capital | **AGPL-3.0** (Community) | Free |
| A researcher, student, or hobbyist | **AGPL-3.0** (Community) | Free |
| Publishing a fork on GitHub | **AGPL-3.0** (Community) | Free |
| A company whose policy forbids AGPL code internally | **Commercial — Internal** | see [tiers](#3-commercial-tiers) |
| Embedding Argus in a product you sell or distribute | **Commercial — OEM** | see [tiers](#3-commercial-tiers) |
| Running Argus as a hosted service for customers | **Commercial — OEM** or **Enterprise** | see [tiers](#3-commercial-tiers) |

**If you run Argus on your own machine to trade your own money, you owe nothing
and never will.** The AGPL only creates obligations when you *distribute* modified
copies or *offer the software to others over a network*.

---

## 2. Community Edition — AGPL-3.0

The full application, under [AGPL-3.0](LICENSE). No feature is withheld from the
Community Edition.

**What you may do:** use it commercially, trade your own capital with it, modify
it, study it, redistribute it, fork it.

**What you must do,** and *only* if you distribute a modified version or expose
it to third parties over a network:

- publish the complete corresponding source of your modified version, under AGPL-3.0;
- preserve copyright and licence notices;
- state what you changed.

This is the reciprocity bargain: improvements to a public work stay public.

---

## 3. Commercial Tiers

A commercial licence removes the AGPL's copyleft and network-disclosure
obligations. It does **not** buy a different or better product — it buys
different *terms*, plus the support attached to each tier.

| | **Internal** | **OEM / Redistribution** | **Enterprise** |
|---|---|---|---|
| **Indicative price** | €490 / year | €4,900 / year | from €14,000 / year |
| Perpetual option (one major version) | €1,490 | €14,900 | on request |
| Use internally, closed-source | ✅ | ✅ | ✅ |
| Modify without publishing changes | ✅ | ✅ | ✅ |
| Redistribute inside your own product | ❌ | ✅ | ✅ |
| Offer as a hosted service to customers | ❌ | ✅ | ✅ |
| Legal entities covered | 1 | 1 + subsidiaries | Group-wide |
| Support | Email, best effort | 5 business days | SLA, private channel |
| Roadmap influence | — | — | ✅ |
| Custom development | at day rate | at day rate | included allowance |

**Services**, independent of any licence tier:

| Service | Indicative rate |
|---|---|
| Integration support, custom exchange or strategy modules | €150 / hour |
| Fixed-scope custom development | quoted per project |

**Free commercial licence** is granted on request to registered non-profits,
accredited academic institutions, and for use in published research. Ask.

---

## 4. Why a company might need a commercial licence

The most common reason has nothing to do with redistribution: **many
organisations ban AGPL-licensed code outright by internal policy**, regardless of
how it is used. A commercial licence resolves that in one line, without your
legal team having to reason about §13 of the AGPL.

The other reasons are the classic ones — embedding Argus in a closed-source
product, or operating it as a service without publishing your modifications.

---

## 5. What a commercial licence does *not* include

Stated plainly, so nothing is inferred that isn't offered:

- **No warranty of profitability.** Argus is analysis and execution software. It
  does not guarantee returns, and past behaviour of any strategy predicts nothing.
- **No investment advice.** See the [Disclaimer](README.md#disclaimer). Argus is a
  tool you configure and operate; the trading decisions and their consequences are
  yours.
- **No indemnity for trading losses**, exchange outages, API failures, or
  third-party model behaviour, except where a signed agreement says otherwise.
- **No rights to third-party components.** Argus depends on separately licensed
  software (CCXT, PyTorch, TimesFM, scikit-learn and others). A commercial licence
  covers *Argus's own code only*; you remain responsible for complying with each
  dependency's licence. See [Third-Party Dependencies](#6-third-party-dependencies).

---

## 6. Third-Party Dependencies

Argus's own source is dual-licensable because its copyright is held entirely by
the project owner. Its **dependencies are not** — each carries its own terms, and
a commercial Argus licence cannot and does not relicense them.

| Dependency | Licence | Commercial redistribution |
|---|---|---|
| CCXT | MIT | ✅ Permissive |
| pandas, NumPy, scikit-learn, PyTorch | BSD-3-Clause | ✅ Permissive |
| requests, yfinance, openai, huggingface-hub, timesfm | Apache-2.0 | ✅ Permissive |
| CustomTkinter, BeautifulSoup4, openpyxl, Pillow | MIT / HPND | ✅ Permissive |
| reportlab | BSD | ✅ Permissive |

**Every dependency is permissively licensed and safe to redistribute in a
commercial product.** No dependency imposes copyleft, field-of-use or
anti-commercial conditions.

> ### Resolved: the vectorbt / Commons Clause problem
>
> Until recently the Instant Backtest depended on `vectorbt`, which ships under
> Apache-2.0 **plus the Commons Clause** — a condition withholding the right to
> *"Sell"* software whose value derives substantially from it. Every published
> vectorbt release (0.26 through 1.1) carries it, so pinning an older version
> was not a way out, and the clause is one AGPL-3.0 §7 does not permit a
> licensee to impose.
>
> It has been **removed**. The backtest now runs on
> [`core/backtest.py`](core/backtest.py), written for this project and covered
> by the same dual licence as the rest of Argus, with no dependencies beyond
> pandas and NumPy. Nothing in the dependency tree now restricts commercial
> sale.

> **Model weights are licensed separately from model code.** The `timesfm`
> *package* is Apache-2.0, but the TimesFM *checkpoints* downloaded from
> Hugging Face carry their own terms. Verify the licence on the specific
> checkpoint you deploy before shipping it commercially.

---

## 7. Contributor terms

All contributions are accepted under the [Contributor License Agreement](CLA.md),
which grants the project owner the right to sublicense contributions under both
AGPL-3.0 and commercial terms. This is what keeps dual licensing possible — without
it, a single contributor could veto every commercial sale.

---

## 8. Getting a Quote

The figures above are **indicative list prices for a first commercial release**,
not a fixed tariff. Real quotes depend on deployment scale, support expectations,
and whether custom development is involved.

📧 **marco.lombardo@gmail.com** — include your company, intended use, and rough
deployment scale, and you will get a concrete quote.

---

*Copyright © 2026 Marco Lombardo. Argus is a dual-licensed work: AGPL-3.0 for the
community, commercial terms on request.*
