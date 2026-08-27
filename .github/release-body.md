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
Unpack and run: no installation, and no Python needed.

### Windows will say the publisher is unknown

It is meant to. These builds carry **no code-signing certificate**, so Microsoft Defender
SmartScreen shows *"Windows protected your PC"* and offers only **Don't run**. Click
**More info**, then **Run anyway**. Nothing is wrong with the download; SmartScreen is
reporting that it has never seen this publisher, which is true.

Because that warning asks you to trust a file you cannot check by looking at it, every
archive ships with a `.sha256` beside it. In PowerShell:

```powershell
Get-FileHash .\Argus-{{VERSION}}-windows-x64.zip -Algorithm SHA256
```

The hash it prints must match the one inside `Argus-{{VERSION}}-windows-x64.zip.sha256`.
If it does, the file is byte for byte what the build produced.

On **macOS**, Gatekeeper refuses an unidentified developer the same way: right-click the
application and choose **Open**, or run `xattr -dr com.apple.quarantine Argus`.

Each archive unpacks to a folder holding the executable and a `licenses/` directory: the
terms of everything Argus is built on, plus an inventory of every native library in the
build and where each licence determination came from. That inventory is generated on the
machine that produced the archive, so it describes what you actually downloaded.

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
