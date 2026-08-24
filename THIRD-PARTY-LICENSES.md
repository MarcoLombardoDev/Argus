# Third-party licences

Argus is licensed **AGPL-3.0-or-later** (see [LICENSE](LICENSE)), with a
commercial licence available separately (see
[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)). That covers the code in this
repository. It does not cover the code Argus is built on, and a
downloadable release is mostly that other code: a Linux build contains
376 native binaries and not one of them was written for Argus.
Argus's own code travels through them as Python bytecode.

This file is the inventory of what those binaries are and what licenses them.

## How this was produced

It was generated, not written from memory, by
[`tools/licence_inventory.py`](tools/licence_inventory.py) run against
the published `Argus-1.0.0-linux-x64.tar.gz` — the
artefact a redistributor actually receives — rather than against the source
tree or a local build. Argus cannot be built faithfully outside CI: its
release installs a CPU-only PyTorch from PyTorch's own package index, and a
build made without that index gets the CUDA wheel and 2.7 GB of NVIDIA
proprietary libraries that no release has ever shipped. That distinction matters:
PyInstaller collects whatever the build machine's linker resolved, so the
contents change when the runner image changes, not when someone edits this
repository. A hand-maintained list would be stale within one CI image bump and
nobody would notice.

Every entry traces to a machine-readable source:

- **Python packages** — the top-level package a binary sits under names its own
  distribution, and that distribution's installed metadata states its licence.
- **Libraries collected from the Linux build machine** — the owning package
  from `dpkg-query`, and that package's `debian/copyright`.
- **Libraries the platform supplies** (the Windows CRT, the OpenSSL that ships
  inside python.org's builds) — identified by name, since no package manager
  owns them.

Two traps in that lookup are worth stating, because both produced wrong answers
before they were caught, and both are handled in the script rather than papered
over:

A `debian/copyright` file enumerates every licence appearing anywhere in the
*source* package, test fixtures and build scripts included. Reporting that
union is alarmist nonsense. What governs a shipped shared library is the
licence of that library's own sources — the stanza whose `Files:` pattern
covers them.

And even the `Files: *` stanza is wrong when one source package builds several
libraries under different terms. util-linux's default stanza says GPL-2+, while
`libuuid`, which these builds do ship, is BSD-3-clause in its own stanza.
Taking the default would have published a wrong answer that looked
authoritative. Those cases are in the script's `REVIEWED` table, each with the
stanza that was read.

Anything the script cannot resolve is reported as **unresolved** rather than
guessed at. A gap you can see is worth more than a plausible-looking entry that
is wrong.

## What Argus depends on directly

Fourteen packages, declared in [`requirements.txt`](requirements.txt), with the
licence each one's own metadata states:

| Package | Version built | Licence (from its metadata) | What Argus uses it for |
|---|---|---|---|
| PyTorch | 2.13.0 | `Apache-2.0 AND BSD-3-Clause AND BSL-1.0 AND MIT` | running the TimesFM forecast model |
| timesfm | 2.0.2 | `Apache-2.0` | the forecast model's own code |
| huggingface-hub | 1.28.0 | `Apache-2.0` | fetching the model checkpoint |
| pandas | 3.0.5 | `BSD-3-Clause` | every price series in the application |
| NumPy | 2.5.2 | `BSD-3-Clause AND 0BSD AND MIT AND Zlib` | the numerics under all of it |
| scikit-learn | 1.9.0 | `BSD-3-Clause` | KNN pattern matching over log-returns |
| SciPy | 1.18.1 | `BSD-3-Clause` | pulled in by scikit-learn |
| CCXT | 4.5.75 | `MIT` | exchange connectivity and order placement |
| yfinance | 1.6.0 | `Apache-2.0` | equity and index price history |
| requests | 2.34.2 | `Apache-2.0` | HTTP, and the certificate bundle behind it |
| openai | 3.3.1 | `Apache-2.0` | the LLM analysis pipeline |
| beautifulsoup4 | 4.15.0 | `MIT` | parsing the pages that pipeline reads |
| CustomTkinter | 6.0.0 | `CC0-1.0` | the interface |
| openpyxl / reportlab | 3.1.5 / 5.0.1 | `MIT` / `BSD-3-Clause` | the Excel and PDF exports |

PyInstaller (`GPL-2.0-or-later WITH Bootloader-exception`) builds the
executable. One dependency was removed outright for its licence: the instant
backtest used to rely on `vectorbt`, which ships under Apache-2.0 *plus the
Commons Clause* — a condition withholding the right to "Sell" software whose
value derives substantially from it, and one AGPL-3.0 §7 does not permit a
licensee to impose. It was replaced by [`core/backtest.py`](core/backtest.py),
written for this project, with no dependencies beyond pandas and NumPy. Do not
reintroduce it.

**Model weights are licensed separately from model code.** The `timesfm`
package is Apache-2.0; the TimesFM checkpoints downloaded from Hugging Face
carry their own terms. Verify the licence on the specific checkpoint you deploy
before shipping it commercially.

## The components that actually constrain redistribution

Most of the inventory below is MIT, BSD and ISC — attribution and nothing more.
Three things are not, and these are the ones worth a decision:

**Three MPL-2.0 distributions** — `certifi`, `orjson` and `tqdm`, all reached
through `requests` and `openai` rather than asked for. MPL-2.0 is file-level
weak copyleft: it does not reach the rest of the application, and it does not
stop Argus being shipped inside a closed product, but it does require that
the source of *those files* be made available to a recipient and that their
notices be kept. They are pure Python, so they appear in `licenses/` rather
than in the native tables below — which is exactly why the tables alone are not
the whole answer.

**The GCC runtime** — `libgcc_s`, `libstdc++`, `libgomp` (OpenMP, which PyTorch
and SciPy both link) and `libobjc`, all GPL-3.0-or-later **with the GCC Runtime
Library Exception 3.1**. The exception is what makes them distributable at all;
without it a GPL-3 library would sit in the middle of every Linux build.
Nothing to do here, but it should not be mistaken for a permissive licence.

**The Microsoft Visual C++ and Universal CRT runtime** (Windows only) — not
open source at all. Redistributable under Microsoft's own redistributable
terms, which is a different legal basis from every other entry in this document
and carries its own conditions.

## What was deliberately removed

**The standard library's `readline` extension.** PyInstaller collected it by
default, and it links `libreadline`, which is **GPL-3.0-or-later with no
linking exception**. The published v1.0.0 Linux archive contains it — it is in
the table below, flagged — which means the archive currently offered for
commercial redistribution contains a GPL-3 library. That is the one combination
the whole commercial tier is supposed to avoid.

`libpython` does not link it; only that module does, and Argus is a windowed
application that never reads a line from an interactive prompt. It and
`rlcompleter` are now excluded in [`Argus.spec`](Argus.spec), so the next
release does not contain it, and
[`tests/test_packaging.py`](tests/test_packaging.py) pins the exclusion so it
cannot silently come back. `libtinfo` leaves with it.

## Licence texts travel with the build

The v1.0.0 archives contained one executable and nothing else. A recursive
search of all three for `LICENSE`, `COPYING` or `NOTICE` returned nothing,
which every BSD and MIT notice in the bundle requires, which the LGPL-2.1
system libraries require in stronger terms, and which Argus's own AGPL
requires as well.

[`tools/collect_licences.py`](tools/collect_licences.py) now assembles them and
the release workflow packages the result as `licenses/` **beside** the
executable. Beside rather than inside, because these are `--onefile` builds:
anything added to the bundle is sealed in the executable and visible only to
somebody who has already run it, which is not what "accompany the object code"
means.

The tree holds one directory per distribution that contributed code, the
interpreter's and Tcl/Tk's own terms — neither is a wheel, so neither has
metadata to read and both are supplied from [`licenses/`](licenses) in this
repository — and, on Linux, the build machine's copyright record for every
system library collected. Which distributions those are is read out of
PyInstaller's own record of the build rather than from a list kept by hand: a
list like that is right the day it is written and wrong the first time a
dependency grows a dependency.

## Full inventory

Counts are files, not projects: one project usually contributes several
binaries. "Evidence" names where the licence came from, so any line here can be
re-checked rather than taken on trust.

### Linux — 376 native binaries

| Component | Files | Licence | Evidence |
|---|---|---|---|
| `CPython` (cpython) | 57 | PSF-2.0 | the Python Software Foundation License, version 2 |
| `libbrotli1` (system) | 2 | MIT | debian/copyright, Files: * stanza |
| `libbsd0` (system) | 1 | BSD-3-Clause AND BSD-2-Clause AND ISC | reviewed: per-file stanzas, all permissive BSD/ISC variants |
| `libbz2-1.0` (system) | 1 | bzip2-1.0.6 | debian/copyright, Files: * stanza |
| `libexpat1` (system) | 1 | MIT | debian/copyright, Files: * stanza |
| `libffi8` (system) | 1 | MIT | debian/copyright, Files: * stanza |
| `libfontconfig1` (system) | 1 | MIT | free-form copyright: 'Permission to use, copy, modify' — Keith Packard, fontconfig |
| `libfreetype6` (system) | 1 | FTL (FreeType License) | debian/copyright, Files: * stanza |
| `libgcc-s1` (system) | 1 | GPL-3.0-or-later WITH GCC-exception-3.1 | free-form copyright: 'version 3.1 of the GCC Runtime Library Exception' |
| `liblzma5` (system) | 1 | public domain | debian/copyright, Files: * stanza |
| `libmd0` (system) | 1 | BSD-3-Clause AND BSD-2-Clause AND ISC | reviewed: per-file stanzas, all permissive BSD/ISC variants |
| `libobjc4` (system) | 1 | GPL-3.0-or-later WITH GCC-exception-3.1 | free-form copyright: 'licensed under ... version 3.1 of the GCC Runtime Library Exception', whose list of covered libraries includes libobjc |
| `libpng16-16t64` (system) | 1 | Libpng | debian/copyright, Files: * stanza |
| `libreadline8t64` (system) | 1 | GPL-3.0-or-later | debian/copyright, Files: * stanza |
| `libsqlite3-0` (system) | 1 | public domain | debian/copyright, Files: * stanza |
| `libssl3t64` (system) | 2 | Apache-2.0 | debian/copyright, Files: * stanza |
| `libstdc++6` (system) | 1 | GPL-3.0-or-later WITH GCC-exception-3.1 | free-form copyright: 'version 3.1 of the GCC Runtime Library Exception' |
| `libtcl8.6` (system) | 1 | TCL (BSD-style) | free-form copyright: 'This software is copyrighted by the Regents of the University of California, Sun Microsystems, Inc., Scriptics Corporation' |
| `libtinfo6` (system) | 1 | MIT | debian/copyright, Files: * stanza |
| `libtk8.6` (system) | 1 | TCL (BSD-style) | free-form copyright: 'This software is copyrighted by the Regents of the University of California, Sun Microsystems, Inc.' |
| `libuuid1` (system) | 1 | BSD-3-Clause | reviewed: Files: libuuid/* — default stanza says GPL-2+ |
| `libx11-6` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxau6` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxdmcp6` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxext6` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxft2` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxrender1` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxss1` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `zlib1g` (system) | 1 | Zlib | debian/copyright, Files: * stanza |
| `aiohttp` (wheel) | 4 | Apache-2.0 AND MIT | the wheel's own distribution metadata |
| `cffi` (wheel) | 1 | MIT | the wheel's own distribution metadata |
| `charset-normalizer` (wheel) | 3 | MIT | the wheel's own distribution metadata |
| `coincurve` (wheel) | 1 | MIT OR Apache-2.0 | the wheel's own distribution metadata |
| `cryptography` (wheel) | 1 | Apache-2.0 OR BSD-3-Clause | the wheel's own distribution metadata |
| `curl_cffi` (wheel) | 1 | MIT | the wheel's own distribution metadata |
| `frozenlist` (wheel) | 1 | Apache-2.0 | the wheel's own distribution metadata |
| `hf-xet` (wheel) | 1 | Apache-2.0 | the wheel's own distribution metadata |
| `jiter` (wheel) | 1 | MIT | the wheel's own distribution metadata |
| `lxml` (wheel) | 7 | BSD-3-Clause | the wheel's own distribution metadata |
| `MarkupSafe` (wheel) | 1 | BSD-3-Clause | the wheel's own distribution metadata |
| `multidict` (wheel) | 1 | Apache License 2.0 | the wheel's own distribution metadata |
| `numpy` (wheel) | 16 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | the wheel's own distribution metadata |
| `orjson` (wheel) | 1 | MPL-2.0 AND (Apache-2.0 OR MIT) | the wheel's own distribution metadata |
| `pandas` (wheel) | 45 | BSD 3-Clause License | the wheel's own distribution metadata |
| `pillow` (wheel) | 25 | MIT-CMU | the wheel's own distribution metadata |
| `propcache` (wheel) | 1 | Apache-2.0 | the wheel's own distribution metadata |
| `protobuf` (wheel) | 1 | 3-Clause BSD License | the wheel's own distribution metadata |
| `pydantic_core` (wheel) | 1 | MIT | the wheel's own distribution metadata |
| `PyYAML` (wheel) | 1 | MIT | the wheel's own distribution metadata |
| `safetensors` (wheel) | 1 | Apache Software License | the wheel's own distribution metadata |
| `scikit-learn` (wheel) | 59 | BSD-3-Clause | the wheel's own distribution metadata |
| `scipy` (wheel) | 100 | BSD License | the wheel's own distribution metadata |
| `torch` (wheel) | 12 | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT | the wheel's own distribution metadata |
| `uvloop` (wheel) | 1 | MIT License | the wheel's own distribution metadata |
| `websockets` (wheel) | 1 | BSD-3-Clause | the wheel's own distribution metadata |
| `yarl` (wheel) | 1 | Apache-2.0 | the wheel's own distribution metadata |

**Flagged for review**

- `libreadline8t64` — GPL-3.0-or-later with no linking exception. Nothing here should be linking it: it arrives only with the standard library's optional readline extension, which the build excludes for exactly this reason. If it appears in this table, that exclusion has stopped working.

## Build-time tools

PyInstaller is a build-time tool, but part of it ships: the bootloader is the
first thing in the executable. It is GPL-2.0-or-later **with the Bootloader
Exception**, which grants unlimited permission to embed the bootloader in a
combined program and distribute that program under terms of your choosing —
which is exactly what a frozen application does. Its `COPYING.txt` travels in
`licenses/` for that reason. Nothing else used only to build Argus appears
in the archive, and so nothing else appears in this document.

## Known gaps

- **Only native binaries are inventoried.** Python code shipped as bytecode is
  not in the tables above; it is covered by the `licenses/` tree, which is
  assembled per distribution rather than per binary. For Argus this is where the MPL-2.0 distributions named above live, and
  they are the reason this bullet is not a formality;
  [`tests/test_third_party_licences.py`](tests/test_third_party_licences.py)
  fails if a copyleft distribution appears that this document does not name.
- **The inventory is per build.** The tables above describe the Linux build
  named at the top. The Windows and macOS archives are inventoried by the same
  script on their own runners, and each archive carries its own copy as
  `licenses/THIRD-PARTY-LICENSES-<platform>.md`. Those are the authoritative
  ones for what was downloaded.
- **Licence determinations are evidence, not opinions.** Each row names where
  it came from so it can be re-checked. They are given in good faith, are
  current as at the version of this document, and are **not a legal opinion**.

## Reproducing this

```
python build.py
python tools/collect_licences.py build/licenses
python tools/licence_inventory.py --bundle linux=build/Argus --markdown out.md
```

Run it on a host of the same family as the release runner — Ubuntu, for the
Linux bundle — or the system-library lookup has nothing to consult and every
such library is reported unresolved.
