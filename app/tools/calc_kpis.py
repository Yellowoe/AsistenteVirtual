# app/tools/calc_kpis.py  (versión corta: tu mismo código, con fixes en aging)

import pandas as pd
from dateutil.relativedelta import relativedelta

def _residual(amount: float, paid: float) -> float:
    return max((amount or 0.0) - (paid or 0.0), 0.0)

def _overdue_days(due_series: pd.Series, ref_date: pd.Timestamp) -> pd.Series:
    # Asegura datetime, calcula días, y SOLO deja positivos (>0)
    due = pd.to_datetime(due_series, errors="coerce")
    days = (ref_date - due).dt.days
    # where>0 evita que NaT se convierta en 0 vencido
    return days.where(days > 0, 0).fillna(0).astype(int)

def aging_buckets_cxc(df: pd.DataFrame, ref_date: pd.Timestamp) -> dict:
    df = df.copy()
    # Normaliza columnas que vamos a usar
    if "amount" not in df.columns and "total_amount" in df.columns:
        df["amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0.0)
    else:
        df["amount"] = pd.to_numeric(df.get("amount", 0.0), errors="coerce").fillna(0.0)
    df["paid_amount"] = pd.to_numeric(df.get("paid_amount", 0.0), errors="coerce").fillna(0.0)
    df["due_date"] = pd.to_datetime(df.get("due_date"), errors="coerce")

    df["residual"] = df.apply(lambda r: _residual(r.get("amount",0.0), r.get("paid_amount",0.0)), axis=1)
    open_items = df[df["residual"] > 0].copy()
    open_items["days_past_due"] = _overdue_days(open_items["due_date"], ref_date)

    # >>> CAMBIO CLAVE: solo contamos vencidas (>0) en los buckets <<<
    overdue = open_items[open_items["days_past_due"] > 0]

    return {
        "0_30": float(overdue[overdue["days_past_due"] <= 30]["residual"].sum()),
        "31_60": float(overdue[(overdue["days_past_due"] > 30) & (overdue["days_past_due"] <= 60)]["residual"].sum()),
        "61_90": float(overdue[(overdue["days_past_due"] > 60) & (overdue["days_past_due"] <= 90)]["residual"].sum()),
        "90_plus": float(overdue[overdue["days_past_due"] > 90]["residual"].sum()),
    }

def aging_buckets_cxp(df: pd.DataFrame, ref_date: pd.Timestamp) -> dict:
    df = df.copy()
    # Normaliza columnas
    amount_col = "total_amount" if "total_amount" in df.columns else "amount"
    df[amount_col] = pd.to_numeric(df.get(amount_col, 0.0), errors="coerce").fillna(0.0)
    df["paid_amount"] = pd.to_numeric(df.get("paid_amount", 0.0), errors="coerce").fillna(0.0)
    df["due_date"] = pd.to_datetime(df.get("due_date"), errors="coerce")

    df["residual"] = df.apply(lambda r: _residual(r.get(amount_col,0.0), r.get("paid_amount",0.0)), axis=1)
    open_items = df[df["residual"] > 0].copy()
    open_items["days_past_due"] = _overdue_days(open_items["due_date"], ref_date)

    # >>> Igual que en CxC: solo vencidas (>0) <<<
    overdue = open_items[open_items["days_past_due"] > 0]

    return {
        "0_30": float(overdue[overdue["days_past_due"] <= 30]["residual"].sum()),
        "31_60": float(overdue[(overdue["days_past_due"] > 30) & (overdue["days_past_due"] <= 60)]["residual"].sum()),
        "61_90": float(overdue[(overdue["days_past_due"] > 60) & (overdue["days_past_due"] <= 90)]["residual"].sum()),
        "90_plus": float(overdue[overdue["days_past_due"] > 90]["residual"].sum()),
    }

def dso(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    days = (end - start).days or 30
    # Asegura numéricos
    amt = pd.to_numeric(df.get("amount", 0.0), errors="coerce").fillna(0.0)
    paid = pd.to_numeric(df.get("paid_amount", 0.0), errors="coerce").fillna(0.0)
    ar_end = float((amt - paid).clip(lower=0.0).sum())
    sales = float(df[(pd.to_datetime(df.get("issue_date"), errors="coerce") >= start) &
                     (pd.to_datetime(df.get("issue_date"), errors="coerce") <= end)]["amount"].sum())
    return round((ar_end / sales) * days, 2) if sales > 0 else None

def dpo(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    amount_col = "total_amount" if "total_amount" in df.columns else "amount"
    days = (end - start).days or 30
    amt = pd.to_numeric(df.get(amount_col, 0.0), errors="coerce").fillna(0.0)
    paid = pd.to_numeric(df.get("paid_amount", 0.0), errors="coerce").fillna(0.0)
    ap_end = float((amt - paid).clip(lower=0.0).sum())
    issue = pd.to_datetime(df.get("issue_date"), errors="coerce")
    purchases = float(df[(issue >= start) & (issue <= end)][amount_col].sum())
    return round((ap_end / purchases) * days, 2) if purchases > 0 else None

def month_window(period_str: str):
    start = pd.Timestamp(f"{period_str}-01")
    end = (start + relativedelta(months=1)) - pd.Timedelta(days=1)
    return start, end, end
