import pandas as pd
from dateutil.relativedelta import relativedelta

def _residual(amount: float, paid: float) -> float:
    return max((amount or 0.0) - (paid or 0.0), 0.0)

def aging_buckets_cxc(df: pd.DataFrame, ref_date: pd.Timestamp) -> dict:
    df = df.copy()
    df["residual"] = df.apply(lambda r: _residual(r.get("amount",0), r.get("paid_amount",0)), axis=1)
    open_items = df[df["residual"] > 0].copy()
    open_items["days_past_due"] = (ref_date - open_items["due_date"]).dt.days.clip(lower=0).fillna(0)
    return {
        "0_30": float(open_items[open_items["days_past_due"]<=30]["residual"].sum()),
        "31_60": float(open_items[(open_items["days_past_due"]>30)&(open_items["days_past_due"]<=60)]["residual"].sum()),
        "61_90": float(open_items[(open_items["days_past_due"]>60)&(open_items["days_past_due"]<=90)]["residual"].sum()),
        "90_plus": float(open_items[open_items["days_past_due"]>90]["residual"].sum()),
    }

def aging_buckets_cxp(df: pd.DataFrame, ref_date: pd.Timestamp) -> dict:
    df = df.copy()
    amount_col = "total_amount" if "total_amount" in df.columns else "amount"
    df["residual"] = df.apply(lambda r: _residual(r.get(amount_col,0), r.get("paid_amount",0)), axis=1)
    open_items = df[df["residual"] > 0].copy()
    open_items["days_past_due"] = (ref_date - open_items["due_date"]).dt.days.clip(lower=0).fillna(0)
    return {
        "0_30": float(open_items[open_items["days_past_due"]<=30]["residual"].sum()),
        "31_60": float(open_items[(open_items["days_past_due"]>30)&(open_items["days_past_due"]<=60)]["residual"].sum()),
        "61_90": float(open_items[(open_items["days_past_due"]>60)&(open_items["days_past_due"]<=90)]["residual"].sum()),
        "90_plus": float(open_items[open_items["days_past_due"]>90]["residual"].sum()),
    }

def dso(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    days = (end - start).days or 30
    ar_end = float(df.apply(lambda r: _residual(r.get("amount",0), r.get("paid_amount",0)), axis=1).sum())
    sales = float(df[(df["issue_date"]>=start) & (df["issue_date"]<=end)]["amount"].sum())
    return round((ar_end / sales) * days, 2) if sales > 0 else None

def dpo(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    amount_col = "total_amount" if "total_amount" in df.columns else "amount"
    days = (end - start).days or 30
    ap_end = float(df.apply(lambda r: _residual(r.get(amount_col,0), r.get("paid_amount",0)), axis=1).sum())
    purchases = float(df[(df["issue_date"]>=start) & (df["issue_date"]<=end)][amount_col].sum())
    return round((ap_end / purchases) * days, 2) if purchases > 0 else None

def month_window(period_str: str):
    start = pd.Timestamp(f"{period_str}-01")
    end = (start + relativedelta(months=1)) - pd.Timedelta(days=1)
    return start, end, end
