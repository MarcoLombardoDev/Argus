"""
ai_analysis_store.py — Argus
AI analysis session persistence and export management.

Each session is saved as JSON in data/ai_analysis/
with name YYYYMMDD_HHMMSS_<n_crypto>crypto.json
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from core.portfolio_manager import PortfolioManager
from core.data_manager import load_settings

# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
AI_ANALYSIS_DIR = BASE_DIR / "data" / "ai_analysis"


def _ensure_dir():
    AI_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# Saving
# ─────────────────────────────────────────────────────────────

def save_ai_session(results: list[dict], meta: dict = None) -> str:
    """
    Saves an AI analysis session to a JSON file.

    Args:
        results: list of dicts with the analysis results
        meta: optional dictionary with additional metadata (provider, model, etc.)

    Returns:
        The session_id (filename without extension) of the saved session.
    """
    _ensure_dir()
    now = datetime.now()
    session_id = now.strftime("%Y%m%d_%H%M%S") + f"_{len(results)}crypto"
    filename = AI_ANALYSIS_DIR / f"{session_id}.json"

    session_data = {
        "session_id": session_id,
        "created_at": now.isoformat(),
        "n_crypto": len(results),
        "meta": meta or {},
        "results": results,
    }

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)
        print(f"[AIStore] Session saved: {filename}")
        return session_id
    except Exception as e:
        print(f"[AIStore] Error saving session: {e}")
        return ""


# ─────────────────────────────────────────────────────────────
# Loading
# ─────────────────────────────────────────────────────────────

def load_all_sessions() -> list[dict]:
    """
    Loads metadata of all saved sessions (without complete results).

    Returns:
        List of dicts with: session_id, created_at, n_crypto, meta, results
        Ordered by descending date (most recent first).
    """
    _ensure_dir()
    sessions = []
    for filepath in sorted(AI_ANALYSIS_DIR.glob("*.json"), reverse=True):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "session_id": data.get("session_id", filepath.stem),
                "created_at": data.get("created_at", ""),
                "n_crypto": data.get("n_crypto", 0),
                "meta": data.get("meta", {}),
                "results": data.get("results", []),  # included for loading convenience
            })
        except Exception as e:
            print(f"[AIStore] Error reading session {filepath.name}: {e}")
    return sessions


def load_session(session_id: str) -> Optional[dict]:
    """
    Loads a complete session by session_id.

    Returns:
        dict with all session data, or None if not found.
    """
    _ensure_dir()
    filepath = AI_ANALYSIS_DIR / f"{session_id}.json"
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[AIStore] Error loading session {session_id}: {e}")
        return None


def delete_session(session_id: str) -> bool:
    """Deletes a session by session_id."""
    filepath = AI_ANALYSIS_DIR / f"{session_id}.json"
    try:
        if filepath.exists():
            filepath.unlink()
            return True
    except Exception as e:
        print(f"[AIStore] Error deleting session {session_id}: {e}")
    return False


def delete_analysis(session_id: str, symbol: str) -> bool:
    """Deletes a single analysis from a session. If the session becomes empty, deletes the file."""
    _ensure_dir()
    filepath = AI_ANALYSIS_DIR / f"{session_id}.json"
    if not filepath.exists():
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        original_len = len(data.get("results", []))
        data["results"] = [r for r in data.get("results", []) if r.get("symbol") != symbol]
        
        if len(data["results"]) == original_len:
            return False  # Not found
            
        if len(data["results"]) == 0:
            filepath.unlink()
            print(f"[AIStore] Session {session_id} deleted because it was empty.")
            return True
            
        data["n_crypto"] = len(data["results"])
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        print(f"[AIStore] Analysis of {symbol} deleted from session {session_id}.")
        return True
    except Exception as e:
        print(f"[AIStore] Error deleting analysis of {symbol} from session {session_id}: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────

def _num(value, default: float = 0.0) -> float:
    """float() that never raises.

    Result fields carry sentinels such as ``"N/A"`` and ``"DISABLED"`` (and
    ``None``) alongside real numbers; a bare float() on those aborted the whole
    CSV/Excel/PDF export.
    """
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return default if value != value else float(value)  # NaN -> default
    try:
        return float(str(value).strip().replace("%", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


def _fng_of(result: dict, default: int = 50):
    """Reads market_context.fng_value defensively (market_context may be None)."""
    ctx = result.get("market_context")
    if isinstance(ctx, dict):
        return ctx.get("fng_value", default)
    return default


def _row_leverage(leverage_cfg: int, curr_p: float, sl_val) -> int:
    """Caps the configured leverage so the stop-loss stays inside the liquidation
    band (80% of margin). Returns at least 1."""
    leverage = max(1, int(leverage_cfg))
    sl = _num(sl_val, default=float("nan"))
    if curr_p > 0 and sl == sl:  # not NaN
        sl_dist = abs(curr_p - sl) / curr_p
        if sl_dist > 0:
            leverage = min(leverage, max(1, int(0.80 / sl_dist)))
    return leverage


def _roi_cell(level, curr_p: float, signal: str, leverage: int) -> str:
    """Formats an SL/TP level as 'price (ROI%)'. Returns 'N/A' when unavailable."""
    if level is None or curr_p <= 0:
        return "N/A"
    val = _num(level, default=float("nan"))
    if val != val:  # NaN
        return "N/A"
    if str(signal).upper() == "SELL":
        change = (curr_p - val) / curr_p
    else:
        change = (val - curr_p) / curr_p
    return f"{val:.4f} ({change * leverage * 100:+.2f}%)"


def _results_to_df(results: list[dict]) -> pd.DataFrame:
    """Converts the results into a pandas DataFrame for export."""
    rows = []
    # Build the settings + sizing helper ONCE. `for_sizing` skips the CCXT client
    # entirely: exporting only needs calculate_sizing(), which is pure maths.
    app_settings = load_settings()
    pm = PortfolioManager.for_sizing(app_settings)
    leverage_cfg = int(app_settings.get("portfolio_manager", {}).get("maxLeverage", 1) or 1)
    if leverage_cfg < 1:
        leverage_cfg = 1

    for r in results:
        adv_sig = str(r.get("signal_1d", "N/A")).upper().strip()
        fng_value = _fng_of(r)

        tfm_pct = _num(r.get("change_pct_1d"))
        pm_pct = _num(r.get("btc_expected_move"))
        ai_pct = _num(r.get("ai_change_pct_1d"), tfm_pct)
        pm_conf = _num(r.get("btc_pred_confidence"), 50.0)
        ai_conf = _num(r.get("confidence"), 50.0)
        tfm_conf = _num(r.get("tfm_confidence"), 50.0)

        _, _, size_mult, _ = pm.calculate_sizing(
            tfm_pct=tfm_pct,
            pm_pct=pm_pct,
            ai_pct=ai_pct,
            fng_value=fng_value,
            pm_conf=pm_conf,
            ai_conf=ai_conf,
            tfm_conf=tfm_conf
        )
        sizing_str = f"{int(size_mult * 100)}%" if size_mult > 0 else "0%"

        # Calculate ROI% — `leverage` is derived per row from leverage_cfg so one
        # tight stop-loss cannot shrink the leverage used for every later row.
        curr_p = _num(r.get("current_price") or r.get("last_price"))
        sl_pct_str = "N/A"
        tp_pct_str = "N/A"
        if curr_p > 0:
            sl_val = r.get("stop_loss")
            tp_val = r.get("take_profit")

            leverage = _row_leverage(leverage_cfg, curr_p, sl_val)
            sl_pct_str = _roi_cell(sl_val, curr_p, adv_sig, leverage)
            tp_pct_str = _roi_cell(tp_val, curr_p, adv_sig, leverage)


        rows.append({
            "Name": r.get("name", ""),
            "Symbol": r.get("symbol", ""),
            "Current Price": r.get("current_price", ""),
            "Target 1d": r.get("target_price_1d", ""),
            "Var% 1d": r.get("change_pct_1d", ""),
            "Signal 1d": r.get("signal_1d", ""),
            "Signal 1d TFM": r.get("timefm_signal_1d", ""),
            "SL Target (ROI%)": sl_pct_str,
            "TP Target (ROI%)": tp_pct_str,
            "Sizing (%)": sizing_str,
            "Confidence": r.get("confidence", ""),
            "Rationale": r.get("rationale", ""),
            "Key Risk": r.get("key_risk", ""),
            "Analyzed At": r.get("analyzed_at", ""),
        })
    return pd.DataFrame(rows)


def export_session_csv(session_id: str, output_path: str) -> bool:
    """
    Exports a session to CSV format.

    Args:
        session_id: session id
        output_path: output file path (.csv)

    Returns:
        True if successful, False otherwise.
    """
    session = load_session(session_id)
    if not session:
        return False
    try:
        df = _results_to_df(session.get("results", []))
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"[AIStore] Exported CSV: {output_path}")
        return True
    except Exception as e:
        print(f"[AIStore] Error exporting CSV: {e}")
        return False


def export_session_excel(session_id: str, output_path: str) -> bool:
    """
    Exports a session to Excel format (.xlsx).

    Args:
        session_id: session id
        output_path: output file path (.xlsx)

    Returns:
        True if successful, False otherwise.
    """
    session = load_session(session_id)
    if not session:
        return False
    try:
        df = _results_to_df(session.get("results", []))
        meta = session.get("meta", {})
        created_at = session.get("created_at", "")
        
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            # Results sheet
            df.to_excel(writer, sheet_name="Results", index=False)
            
            # Metadata sheet
            meta_rows = [
                ["Session ID", session_id],
                ["Analysis Date", created_at],
                ["N. Crypto", session.get("n_crypto", 0)],
                ["Provider", meta.get("ai_provider", "")],
                ["Model", meta.get("ai_model", "")],
            ]
            df_meta = pd.DataFrame(meta_rows, columns=["Parameter", "Value"])
            df_meta.to_excel(writer, sheet_name="Session Info", index=False)
            
            # Agent debug sheet (if available)
            debug_rows = []
            for r in session.get("results", []):
                debug = r.get("debug", {})
                if debug:
                    debug_rows.append({
                        "Symbol": r.get("symbol", ""),
                        "Market Analyst": debug.get("market_analysis", ""),
                        "News Analyst": debug.get("news_analysis", ""),
                        "Fundamentals Analyst": debug.get("fundamentals_analysis", ""),
                        "Bull Researcher": debug.get("bull_case", ""),
                        "Bear Researcher": debug.get("bear_case", ""),
                    })
            if debug_rows:
                df_debug = pd.DataFrame(debug_rows)
                df_debug.to_excel(writer, sheet_name="Agent Analysis", index=False)

        print(f"[AIStore] Exported Excel: {output_path}")
        return True
    except Exception as e:
        print(f"[AIStore] Error exporting Excel: {e}")
        return False


def export_session_pdf(session_id: str, output_path: str) -> bool:
    """
    Exports a session to PDF format (requires reportlab).

    Args:
        session_id: session id
        output_path: output file path (.pdf)

    Returns:
        True if successful, False otherwise. Returns False if reportlab is not installed.
    """
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph,
            Spacer, HRFlowable
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        print("[AIStore] reportlab is not installed. Use 'pip install reportlab'.")
        return False

    session = load_session(session_id)
    if not session:
        return False

    try:
        doc = SimpleDocTemplate(
            output_path,
            pagesize=landscape(A4),
            rightMargin=1*cm, leftMargin=1*cm,
            topMargin=1.5*cm, bottomMargin=1.5*cm,
        )
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle("title", parent=styles["Title"],
                                      fontSize=16, spaceAfter=6)
        sub_style = ParagraphStyle("sub", parent=styles["Normal"],
                                    fontSize=9, textColor=colors.gray, spaceAfter=12)
        
        meta = session.get("meta", {})
        story.append(Paragraph("👁️ ARGUS — Advanced AI Crypto Analysis", title_style))
        story.append(Paragraph(
            f"Date: {session.get('created_at', '')} | Provider: {meta.get('ai_provider','')} | "
            f"Model: {meta.get('ai_model','')} | Analyzed Crypto: {session.get('n_crypto',0)}",
            sub_style
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
        story.append(Spacer(1, 0.3*cm))

        # Results table
        results = session.get("results", [])

        header = ["Name", "Symbol", "Current\nPrice", "Target\n1d", "Var%\n1d",
                  "Sig\n1d", "TFM\n1d", "SL\n(%)", "TP\n(%)", "Sizing\n(%)", "Rationale"]

        def fmt_price(p):
            if p is None: return "N/A"
            v = _num(p, default=float("nan"))
            if v != v: return "N/A"
            if v >= 1000: return f"${v:,.2f}"
            elif v >= 1: return f"${v:.4f}"
            else: return f"${v:.6f}"

        def fmt_pct(p):
            if p is None: return "N/A"
            v = _num(p, default=float("nan"))
            if v != v: return "N/A"
            return f"{'+' if v >= 0 else ''}{v:.2f}%"

        cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7, leading=9)

        # Build settings + sizing helper once, offline (see _results_to_df).
        app_settings = load_settings()
        pm = PortfolioManager.for_sizing(app_settings)
        leverage_cfg = int(app_settings.get("portfolio_manager", {}).get("maxLeverage", 1) or 1)
        if leverage_cfg < 1: leverage_cfg = 1

        table_data = [header]
        for r in results:
            adv_sig = str(r.get("signal_1d", "N/A")).upper().strip()
            fng_value = _fng_of(r)

            tfm_pct = _num(r.get("change_pct_1d"))
            pm_pct = _num(r.get("btc_expected_move"))
            ai_pct = _num(r.get("ai_change_pct_1d"), tfm_pct)
            pm_conf = _num(r.get("btc_pred_confidence"), 50.0)
            ai_conf = _num(r.get("confidence"), 50.0)
            tfm_conf = _num(r.get("tfm_confidence"), 50.0)


            _, _, size_mult, _ = pm.calculate_sizing(
                tfm_pct=tfm_pct,
                pm_pct=pm_pct,
                ai_pct=ai_pct,
                fng_value=fng_value,
                pm_conf=pm_conf,
                ai_conf=ai_conf,
                tfm_conf=tfm_conf
            )
            sizing_str = f"{int(size_mult * 100)}%" if size_mult > 0 else "0%"
            
            curr_p = _num(r.get("current_price") or r.get("last_price"))
            # Per-row leverage derived from the configured cap — never carried
            # over from the previous row.
            leverage = _row_leverage(leverage_cfg, curr_p, r.get("stop_loss"))

            rationale = str(r.get("rationale", "") or "")
            row = [
                Paragraph(str(r.get("name", ""))[:20], cell_style),
                Paragraph(str(r.get("symbol", "")), cell_style),
                Paragraph(fmt_price(r.get("current_price")), cell_style),
                Paragraph(fmt_price(r.get("target_price_1d")), cell_style),
                Paragraph(fmt_pct(r.get("change_pct_1d")), cell_style),
                Paragraph(str(r.get("signal_1d", "N/A")), cell_style),
                Paragraph(str(r.get("timefm_signal_1d", "N/A")), cell_style),
                Paragraph(_roi_cell(r.get("stop_loss"), curr_p, adv_sig, leverage), cell_style),
                Paragraph(_roi_cell(r.get("take_profit"), curr_p, adv_sig, leverage), cell_style),
                Paragraph(sizing_str, cell_style),
                Paragraph((rationale[:80] + "...") if len(rationale) > 80 else rationale, cell_style),
            ]
            table_data.append(row)

        col_widths = [3.5*cm, 1.6*cm, 2.0*cm, 1.8*cm, 1.4*cm, 1.2*cm, 1.2*cm, 1.3*cm, 1.3*cm, 1.3*cm, 9.4*cm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.Color(0.47, 0.51, 0.99)),
            ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,0), 8),
            ("ALIGN",      (0,0), (-1,-1), "CENTER"),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.Color(0.95,0.95,0.98), colors.white]),
            ("GRID",       (0,0), (-1,-1), 0.5, colors.lightgrey),
            ("FONTSIZE",   (0,1), (-1,-1), 7),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(table)

        doc.build(story)
        print(f"[AIStore] Exported PDF: {output_path}")
        return True

    except Exception as e:
        print(f"[AIStore] Error exporting PDF: {e}")
        return False
