**Argus — Advanced Market Forecast & AI Analysis.** Quantitative price forecasting and
AI-driven analysis of cryptocurrency assets, with an integrated portfolio manager.

- **Forecast** — Google Research's TimesFM 2.5 foundation model for temporal prediction,
  and KNN-DTW pattern matching over normalised log-returns.
- **Analyse** — a cooperative multi-agent LLM pipeline that debates the qualitative case,
  constrained by a built-in instant backtester so decisions rest on real evidence.
- **Execute** — a portfolio manager on CCXT for derivatives exchanges, with an
  institutional-grade money-management framework and an autonomous auto-trading scheduler.

⚠️ The autonomous workflow currently trades **BTC only**. Argus places real orders on real
exchanges: read the Disclaimer in the README before pointing it at a funded account.

## Download

| Platform | File |
|---|---|
| Windows (x64) | `Argus-{{VERSION}}-windows-x64.zip` |
| macOS (Apple silicon) | `Argus-{{VERSION}}-macos-arm64.zip` |
| Linux (x64) | `Argus-{{VERSION}}-linux-x64.tar.gz` |

Each archive is built on that platform's own runner — no cross-compilation, no emulation.
Unpack and run: no installation, and no Python needed. The builds are **unsigned**, so
Windows SmartScreen and macOS Gatekeeper warn on first launch.

Running from source instead is described in the
[README](https://github.com/MarcoLombardoDev/Argus/blob/{{TAG}}/README.md).

## Changes

See [CHANGELOG.md](https://github.com/MarcoLombardoDev/Argus/blob/{{TAG}}/CHANGELOG.md).

## Licence

Licensed **AGPL-3.0-or-later** — see
[LICENSE](https://github.com/MarcoLombardoDev/Argus/blob/{{TAG}}/LICENSE). A commercial
licence, without the AGPL's obligations, is available for closed-source and redistribution
use: see
[COMMERCIAL-LICENSE.md](https://github.com/MarcoLombardoDev/Argus/blob/{{TAG}}/COMMERCIAL-LICENSE.md).
