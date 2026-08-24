# Argus — Advanced Market Forecast & AI Analysis
# Copyright (C) 2026 Marco Lombardo
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Distributed WITHOUT ANY WARRANTY; see LICENSE for the full terms.
# A commercial licence, without the AGPL's obligations, is available for use
# in proprietary or closed-source products — see COMMERCIAL-LICENSE.md.

"""The check the release workflow runs against every bundle it builds.

``--version`` is not a smoke test. argparse prints the version and exits
during argument parsing, before Tk is imported and before a single one of the
product's own modules is loaded, so it proves the frozen interpreter and the
bundled standard library work and nothing else. A bundle whose Tcl/Tk
libraries were not collected passes it. So does one that cannot save a file.
Both then fail on the user's machine, after the release is published.

Two things are checked here instead, because these are the two ways a frozen
bundle actually breaks:

**The toolkit starts.** Creating a Tk root is what makes Tcl go looking for
its script library and Tk for its own, and both are data directories that
PyInstaller has to have collected. The windowing system is reported rather
than assumed — a Linux bundle must come up on ``x11``, and the workflow fails
the build if it does not, because "Tk started" under some fallback is exactly
the result that would hide a broken bundle.

**A file is written and read back.** This is where a frozen application
breaks: a data directory PyInstaller did not collect, a shared library it did
not find. Those failures happen the first time a user saves, not at startup,
and the test suite cannot see them either — it runs against an installed
package, where nothing is missing.

Nothing is left behind: everything is written inside a temporary directory
that goes away with it. A smoke test that litters the user's disk is its own
bug report.
"""

from __future__ import annotations

from core.version import APP_NAME, __version__


def _toolkit() -> list[str]:
    """Start Tk for real and report what backend it came up on.

    Withdrawn immediately: the point is that the toolkit loaded, not that
    anything is shown, and a window flashing up on a build runner would be a
    nuisance at best. ``destroy`` runs whatever happens, so the process can
    still exit cleanly when the report is being written.
    """
    import tkinter

    root = tkinter.Tk()
    try:
        root.withdraw()
        return [
            f"windowing system: {root.tk.call('tk', 'windowingsystem')}",
            f"tk version: {root.tk.call('info', 'patchlevel')}",
        ]
    finally:
        root.destroy()


def _round_trip() -> str:
    """Run a backtest, then write and read back both export formats.

    Argus's bundle is the one where this matters most, because it is almost
    entirely native code: torch, NumPy, SciPy, pandas and scikit-learn between
    them account for the great majority of the 376 libraries in a Linux
    archive, and any one of them can be collected in a state that imports and
    then fails on first use.

    So the check runs a tensor operation — the cheapest thing that proves
    libtorch actually loaded rather than merely being present — puts a price
    series through the product's own backtester, and writes the two formats
    the export panel offers, through the same engines it uses. It deliberately
    does not go through ``ai_analysis_store``: those functions persist a
    session next to the executable, and a smoke test must not leave a data
    directory inside the thing being packaged.
    """
    import tempfile
    from pathlib import Path

    import numpy as np
    import pandas as pd
    import torch

    from core.backtest import run_signal_backtest

    if float(torch.ones(4).sum()) != 4.0:
        raise RuntimeError("torch loaded but does not compute")

    # A deterministic series: no random seed to depend on, and a shape with
    # enough turns in it that entries and exits both fire.
    close = pd.Series(100 + 10 * np.sin(np.linspace(0, 8 * np.pi, 512)))
    fast = close.rolling(8).mean()
    slow = close.rolling(32).mean()
    result = run_signal_backtest(close, fast > slow, fast < slow)
    if not np.isfinite(result.total_return) or not result.trades_count:
        raise RuntimeError(f"the backtest produced no usable result: {result}")

    frame = pd.DataFrame(
        {
            "Symbol": ["SELF/CHECK"],
            # total_return is a fraction; the export panel shows percentages.
            "Return %": [round(float(result.total_return) * 100, 4)],
            "Trades": [int(result.trades_count)],
        }
    )

    with tempfile.TemporaryDirectory(prefix="argus-self-check-") as directory:
        spreadsheet = Path(directory) / "self-check.xlsx"
        with pd.ExcelWriter(spreadsheet, engine="openpyxl") as writer:
            frame.to_excel(writer, sheet_name="Results", index=False)
        reloaded = pd.read_excel(spreadsheet, sheet_name="Results")
        if list(reloaded["Symbol"]) != ["SELF/CHECK"]:
            raise RuntimeError("the spreadsheet came back changed")

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

        document = Path(directory) / "self-check.pdf"
        SimpleDocTemplate(str(document), pagesize=A4).build(
            [
                Paragraph("Argus self-check", getSampleStyleSheet()["Title"]),
                Table([list(frame.columns)] + frame.values.tolist()),
            ]
        )
        # reportlab's fonts are package data; a bundle missing them writes a
        # file that is not a PDF, or none at all.
        written = document.read_bytes()
        if not written.startswith(b"%PDF-") or b"/Page" not in written:
            raise RuntimeError("what reportlab wrote is not a PDF")
        pdf_size, xlsx_size = len(written), spreadsheet.stat().st_size

    return (
        f"backtested {len(close)} bars over {result.trades_count} trades, "
        f"wrote a {xlsx_size}-byte spreadsheet and a {pdf_size}-byte PDF, "
        f"read both back"
    )


def run(report_path: str | None = None) -> int:
    """Run the check, print the report, and return an exit code.

    The report is written to a file as well as printed because two of these
    three products are built ``--windowed`` on Windows, where the process has
    no stdout at all and ``print`` is a no-op. Parsing stdout would work on
    Linux and macOS and silently check nothing on Windows, which is the
    platform whose bundles are least like the machine they were built on.
    """
    lines = [f"{APP_NAME} {__version__}"]
    ok = True

    try:
        lines += _toolkit()
    except Exception as exc:  # noqa: BLE001 - the report is the error handler
        lines.append(f"windowing system: FAILED — {exc}")
        ok = False

    try:
        lines.append(f"round trip: {_round_trip()}")
    except Exception as exc:  # noqa: BLE001 - as above
        lines.append(f"round trip: FAILED — {exc}")
        ok = False

    report = "\n".join(lines)
    print(report)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(report + "\n")
    return 0 if ok else 1
