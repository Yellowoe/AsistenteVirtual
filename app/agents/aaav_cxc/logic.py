from ..base import BaseAgent
from ...state import GlobalState
from ...tools.excel_io import read_excel_required
from ...tools.calc_kpis import aging_buckets_cxc, dso, month_window
from ...tools.schema_validate import validate_with
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime

REQUIRED = [
    "invoice_id",
    "customer",
    "issue_date",
    "due_date",
    "amount",
    "paid_amount",
    "payment_date",
]
DEFAULT_PATH = "data/cxc/invoices.xlsx"
SCHEMA = "app/schemas/aaav_cxc_schema.json"

# -----------------------------
# Enriquecimiento de datos
# -----------------------------

def _enrich_df(df: pd.DataFrame, ref_date: datetime) -> pd.DataFrame:
    df = df.copy()
    # Fechas
    for col in ["issue_date", "due_date", "payment_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Saldos
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["paid_amount"] = pd.to_numeric(df["paid_amount"], errors="coerce").fillna(0.0)
    df["outstanding"] = (df["amount"] - df["paid_amount"]).clip(lower=0.0)

    # Días
    df["days_overdue"] = (ref_date - df["due_date"]).dt.days
    df["days_overdue"] = df["days_overdue"].fillna(0).astype(int)
    df["days_overdue"] = df["days_overdue"].where(df["days_overdue"] > 0, 0)

    df["days_to_due"] = (df["due_date"] - ref_date).dt.days
    df["days_to_due"] = df["days_to_due"].fillna(0).astype(int)

    # Estado
    conditions = [
        (df["outstanding"] <= 0),
        (df["outstanding"] > 0) & (df["days_overdue"] == 0) & (df["days_to_due"] >= 0),
        (df["outstanding"] > 0) & (df["days_overdue"] > 0),
    ]
    choices = ["paid/zero", "open_on_time", "overdue"]
    df["status"] = np.select(conditions, choices, default="open")
    return df

# -----------------------------
# Acciones soportadas (API)
# -----------------------------

def _act_metrics(df: pd.DataFrame, period: str, start, end, ref_date) -> Dict[str, Any]:
    aging = aging_buckets_cxc(df, ref_date)
    kpi_dso = dso(df, start, end)
    payload = {"period": period, "aging": aging, "kpi": {"DSO": kpi_dso}, "incidents": []}
    validate_with(SCHEMA, payload)
    # Mirror top-level para compatibilidad con av_gerente
    return {"summary": "CxC calculado", "data": payload, "dso": kpi_dso}


def _act_top_overdue(df_en: pd.DataFrame, n: int = 10) -> Dict[str, Any]:
    sub = df_en[(df_en["outstanding"] > 0) & (df_en["days_overdue"] > 0)]
    sub = sub.sort_values(["days_overdue", "outstanding"], ascending=[False, False]).head(int(n))
    table = sub[["invoice_id", "customer", "due_date", "days_overdue", "outstanding"]].copy()
    return {
        "summary": f"Top {len(table)} facturas vencidas (más urgentes)",
        "table": table.to_dict(orient="records"),
    }


def _act_due_soon(df_en: pd.DataFrame, days: int = 7) -> Dict[str, Any]:
    sub = df_en[
        (df_en["outstanding"] > 0) & (df_en["days_to_due"] >= 0) & (df_en["days_to_due"] <= int(days))
    ]
    sub = sub.sort_values(["days_to_due", "outstanding"], ascending=[True, False])
    table = sub[["invoice_id", "customer", "due_date", "days_to_due", "outstanding"]].copy()
    return {
        "summary": f"Facturas que vencen en ≤ {int(days)} días",
        "table": table.to_dict(orient="records"),
    }


def _act_customer_balance(df_en: pd.DataFrame, customer: str) -> Dict[str, Any]:
    sub = df_en[
        (df_en["customer"].astype(str).str.strip().str.lower() == str(customer).strip().lower())
        & (df_en["outstanding"] > 0)
    ]
    total = float(sub["outstanding"].sum()) if not sub.empty else 0.0
    table = sub[["invoice_id", "due_date", "days_overdue", "outstanding"]].copy()
    return {
        "summary": f"Saldo pendiente del cliente '{customer}': {total:.2f}",
        "total_outstanding": total,
        "table": table.to_dict(orient="records"),
    }


def _act_list_open(df_en: pd.DataFrame) -> Dict[str, Any]:
    sub = df_en[(df_en["outstanding"] > 0)].sort_values(
        ["status", "days_overdue", "outstanding"], ascending=[True, False, False]
    )
    table = sub[["invoice_id", "customer", "due_date", "status", "days_overdue", "outstanding"]].copy()
    return {"summary": f"{len(table)} facturas abiertas", "table": table.to_dict(orient="records")}


# -----------------------------
# Agente ejecutor
# -----------------------------
class Agent(BaseAgent):
    name = "aaav_cxc"
    role = "operational"

    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        """
        Espera en payload:
          - period: "YYYY-MM"
          - path: opcional, ruta Excel (real time)
          - action: str en {"metrics","top_overdue","due_soon","customer_balance","list_open"}
          - params: dict con parámetros de la acción (n, days, customer, ...)
        """
        payload = task.get("payload", {}) or {}
        period: str = payload.get("period", state.period)
        path: str = payload.get("path", DEFAULT_PATH)
        action: str = (payload.get("action") or "metrics").strip()
        params: Dict[str, Any] = payload.get("params", {}) or {}

        try:
            start, end, ref_date = month_window(period)
            df = read_excel_required(path, REQUIRED)

            # Siempre calculamos métricas base (para que el gerente pueda agregarlas)
            base = _act_metrics(df, period, start, end, ref_date)  # incluye dso top-level

            # Si solo pidieron métricas:
            if action == "metrics":
                return {"agent": self.name, **base}

            # Para acciones de lista, enriquecemos
            df_en = _enrich_df(df, ref_date)

            if action == "top_overdue":
                out = _act_top_overdue(df_en, n=params.get("n", 10))
            elif action == "due_soon":
                out = _act_due_soon(df_en, days=params.get("days", 7))
            elif action == "customer_balance":
                cust = params.get("customer")
                if not cust:
                    return {"agent": self.name, "error": "Falta 'customer' en params"}
                out = _act_customer_balance(df_en, customer=cust)
            elif action == "list_open":
                out = _act_list_open(df_en)
            else:
                return {"agent": self.name, "error": f"Acción desconocida: {action}"}

            # Devolvemos métricas base + resultado de la acción + mirror DSO top-level
            return {
                "agent": self.name,
                "summary": f"CxC ejecutado: {action}",
                "data": base["data"],
                "dso": base.get("dso"),  # espejo top-level compatible con av_gerente
                "result": {"action": action, **out},
            }

        except Exception as e:
            return {
                "agent": self.name,
                "error": str(e),
                "needs": {"path": path, "required_cols": REQUIRED},
            }
