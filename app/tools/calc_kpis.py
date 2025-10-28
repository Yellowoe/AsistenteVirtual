# app/tools/calc_kpis.py
# (versión con compatibilidad de período y fixes de aging/DPO/DSO)

from __future__ import annotations
import re
import pandas as pd
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo

CR_TZ = ZoneInfo("America/Costa_Rica")
_RE_YYYY_MM = re.compile(r"^\d{4}-\d{2}$")

# -----------------------------
# Helpers de período / fechas
# -----------------------------
def _to_cr_tz(ts: pd.Timestamp) -> pd.Timestamp:
    """Asegura TZ America/Costa_Rica en un Timestamp (conversión si trae otra TZ)."""
    if ts.tzinfo is None:
        return ts.tz_localize(CR_TZ)
    return ts.tz_convert(CR_TZ)

def _as_yyyymm(period) -> str:
    """
    Devuelve 'YYYY-MM' aceptando:
      - str 'YYYY-MM'
      - dict con keys {'text','start','end',...} (periodo unificado)
    """
    # 1) Ya es string YYYY-MM
    if isinstance(period, str) and _RE_YYYY_MM.match(period):
        return period

    # 2) Es dict (nuevo formato unificado)
    if isinstance(period, dict):
        t = (period.get("text") or "").strip()
        if _RE_YYYY_MM.match(t):
            return t
        start = period.get("start")
        if start:
            dt = pd.Timestamp(start)
            dt = _to_cr_tz(dt)
            return f"{dt.year:04d}-{dt.month:02d}"

    # 3) Si no calza, error claro
    raise ValueError(f"Periodo no soportado para YYYY-MM: {period!r}")

def month_window(period) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """
    Devuelve (start_dt, end_dt, ref_dt) como pandas Timestamps en TZ CR
    a partir de:
      - 'YYYY-MM' (legacy)
      - dict unificado {'text','start','end','tz',...} (nuevo)
    """
    period_str = _as_yyyymm(period)

    # Primer día del mes a las 00:00:00
    start = pd.Timestamp(f"{period_str}-01")
    start = _to_cr_tz(start)

    # Último día del mes a las 23:59:59
    # (start + 1 mes) - 1 segundo
    end = (start + relativedelta(months=1)) - pd.Timedelta(seconds=1)
    end = end.replace(hour=23, minute=59, second=59)

    # Fecha de referencia (día 15 a las 12:00) — útil para aging
    ref_dt = start + pd.offsets.Day(14) + pd.Timedelta(hours=12)
    return start, end, ref_dt

# -----------------------------
# Funciones comunes
# -----------------------------
def _residual(amount: float, paid: float) -> float:
    return max((amount or 0.0) - (paid or 0.0), 0.0)

def _overdue_days(due_series: pd.Series, ref_date: pd.Timestamp) -> pd.Series:
    # Asegura datetime, calcula días, y SOLO deja positivos (>0)
    due = pd.to_datetime(due_series, errors="coerce")
    # alineamos TZ para evitar offsets raros
    if getattr(ref_date, "tzinfo", None) is not None:
        due = due.dt.tz_localize(ref_date.tz, nonexistent="NaT", ambiguous="NaT") if due.dt.tz is None else due.dt.tz_convert(ref_date.tz)
    days = (ref_date - due).dt.days
    return days.where(days > 0, 0).fillna(0).astype(int)

# -----------------------------
# Aging (CxC / CxP)
# -----------------------------
def aging_buckets_cxc(df: pd.DataFrame, ref_date: pd.Timestamp) -> dict:
    df = df.copy()
    # Normaliza columnas que vamos a usar
    if "amount" not in df.columns and "total_amount" in df.columns:
        df["amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0.0)
    else:
        df["amount"] = pd.to_numeric(df.get("amount", 0.0), errors="coerce").fillna(0.0)
    df["paid_amount"] = pd.to_numeric(df.get("paid_amount", 0.0), errors="coerce").fillna(0.0)
    df["due_date"] = pd.to_datetime(df.get("due_date"), errors="coerce")

    df["residual"] = df.apply(lambda r: _residual(r.get("amount", 0.0), r.get("paid_amount", 0.0)), axis=1)
    open_items = df[df["residual"] > 0].copy()
    ref_date = _to_cr_tz(pd.Timestamp(ref_date))
    open_items["days_past_due"] = _overdue_days(open_items["due_date"], ref_date)

    # Solo vencidas (>0)
    overdue = open_items[open_items["days_past_due"] > 0]

    return {
        "0_30": float(overdue[overdue["days_past_due"] <= 30]["residual"].sum()),
        "31_60": float(overdue[(overdue["days_past_due"] > 30) & (overdue["days_past_due"] <= 60)]["residual"].sum()),
        "61_90": float(overdue[(overdue["days_past_due"] > 60) & (overdue["days_past_due"] <= 90)]["residual"].sum()),
        "90_plus": float(overdue[overdue["days_past_due"] > 90]["residual"].sum()),
    }

def aging_buckets_cxp(df: pd.DataFrame, ref_date: pd.Timestamp) -> dict:
    df = df.copy()
    amount_col = "total_amount" if "total_amount" in df.columns else "amount"
    df[amount_col] = pd.to_numeric(df.get(amount_col, 0.0), errors="coerce").fillna(0.0)
    df["paid_amount"] = pd.to_numeric(df.get("paid_amount", 0.0), errors="coerce").fillna(0.0)
    df["due_date"] = pd.to_datetime(df.get("due_date"), errors="coerce")

    df["residual"] = df.apply(lambda r: _residual(r.get(amount_col, 0.0), r.get("paid_amount", 0.0)), axis=1)
    open_items = df[df["residual"] > 0].copy()
    ref_date = _to_cr_tz(pd.Timestamp(ref_date))
    open_items["days_past_due"] = _overdue_days(open_items["due_date"], ref_date)

    overdue = open_items[open_items["days_past_due"] > 0]

    return {
        "0_30": float(overdue[overdue["days_past_due"] <= 30]["residual"].sum()),
        "31_60": float(overdue[(overdue["days_past_due"] > 30) & (overdue["days_past_due"] <= 60)]["residual"].sum()),
        "61_90": float(overdue[(overdue["days_past_due"] > 60) & (overdue["days_past_due"] <= 90)]["residual"].sum()),
        "90_plus": float(overdue[overdue["days_past_due"] > 90]["residual"].sum()),
    }

# -----------------------------
# KPIs (DSO / DPO)
# -----------------------------
def dso(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    start = _to_cr_tz(pd.Timestamp(start)); end = _to_cr_tz(pd.Timestamp(end))
    days = (end - start).days or 30

    amt = pd.to_numeric(df.get("amount", 0.0), errors="coerce").fillna(0.0)
    paid = pd.to_numeric(df.get("paid_amount", 0.0), errors="coerce").fillna(0.0)
    ar_end = float((amt - paid).clip(lower=0.0).sum())

    issue = pd.to_datetime(df.get("issue_date"), errors="coerce")
    if issue.dt.tz is None:
        issue = issue.dt.tz_localize(CR_TZ)
    sales = float(df[(issue >= start) & (issue <= end)]["amount"].sum())

    return round((ar_end / sales) * days, 2) if sales > 0 else None

def dpo(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    start = _to_cr_tz(pd.Timestamp(start)); end = _to_cr_tz(pd.Timestamp(end))
    amount_col = "total_amount" if "total_amount" in df.columns else "amount"
    days = (end - start).days or 30

    amt = pd.to_numeric(df.get(amount_col, 0.0), errors="coerce").fillna(0.0)
    paid = pd.to_numeric(df.get("paid_amount", 0.0), errors="coerce").fillna(0.0)
    ap_end = float((amt - paid).clip(lower=0.0).sum())

    issue = pd.to_datetime(df.get("issue_date"), errors="coerce")
    if issue.dt.tz is None:
        issue = issue.dt.tz_localize(CR_TZ)
    purchases = float(df[(issue >= start) & (issue <= end)][amount_col].sum())

    return round((ap_end / purchases) * days, 2) if purchases > 0 else None
