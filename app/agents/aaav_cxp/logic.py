from ..base import BaseAgent
from ...state import GlobalState
from ...tools.excel_io import read_excel_required
from ...tools.calc_kpis import aging_buckets_cxp, dpo, month_window
from ...tools.schema_validate import validate_with
from typing import Dict, Any
import pandas as pd
import numpy as np
from datetime import datetime

REQUIRED = [
    "invoice_id",
    "supplier",
    "issue_date",
    "due_date",
    "base_amount",
    "tax",
    "total_amount",
    "paid_amount",
    "payment_date",
]
DEFAULT_PATH = "data/cxp/cxp_invoices.xlsx"
SCHEMA = "app/schemas/aaav_cxp_schema.json"

# -----------------------------
# Enriquecimiento de datos (CxP)
# -----------------------------

def _enrich_df(df: pd.DataFrame, ref_date: datetime) -> pd.DataFrame:
    df = df.copy()
    # Fechas
    for col in ["issue_date", "due_date", "payment_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Montos
    for col in ["base_amount", "tax", "total_amount", "paid_amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Pendiente
    # Preferimos total_amount si existe; si no, base + tax
    if "total_amount" in df.columns:
        gross = df["total_amount"]
    else:
        gross = df.get("base_amount", 0.0) + df.get("tax", 0.0)
    df["outstanding"] = (gross - df.get("paid_amount", 0.0)).clip(lower=0.0)

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
    aging = aging_buckets_cxp(df, ref_date)
    kpi_dpo = dpo(df, start, end)
    payload = {"period": period, "aging": aging, "kpi": {"DPO": kpi_dpo}}
    validate_with(SCHEMA, payload)
    # Mirror top-level para compatibilidad con av_gerente
    return {"summary": "CxP calculado", "data": payload, "dpo": kpi_dpo}


def _act_top_overdue(df_en: pd.DataFrame, n: int = 10) -> Dict[str, Any]:
    sub = df_en[(df_en["outstanding"] > 0) & (df_en["days_overdue"] > 0)]
    sub = sub.sort_values(["days_overdue", "outstanding"], ascending=[False, False]).head(int(n))
    table = sub[["invoice_id", "supplier", "due_date", "days_overdue", "outstanding"]].copy()
    return {
        "summary": f"Top {len(table)} facturas por pagar vencidas (más urgentes)",
        "table": table.to_dict(orient="records"),
    }


def _act_due_soon(df_en: pd.DataFrame, days: int = 7) -> Dict[str, Any]:
    sub = df_en[
        (df_en["outstanding"] > 0) & (df_en["days_to_due"] >= 0) & (df_en["days_to_due"] <= int(days))
    ]
    sub = sub.sort_values(["days_to_due", "outstanding"], ascending=[True, False])
    table = sub[["invoice_id", "supplier", "due_date", "days_to_due", "outstanding"]].copy()
    return {
        "summary": f"Facturas por pagar que vencen en ≤ {int(days)} días",
        "table": table.to_dict(orient="records"),
    }


def _act_supplier_balance(df_en: pd.DataFrame, supplier: str) -> Dict[str, Any]:
    sub = df_en[
        (df_en["supplier"].astype(str).str.strip().str.lower() == str(supplier).strip().lower())
        & (df_en["outstanding"] > 0)
    ]
    total = float(sub["outstanding"].sum()) if not sub.empty else 0.0
    table = sub[["invoice_id", "due_date", "days_overdue", "outstanding"]].copy()
    return {
        "summary": f"Saldo pendiente con el proveedor '{supplier}': {total:.2f}",
        "total_outstanding": total,
        "table": table.to_dict(orient="records"),
    }


def _act_list_open(df_en: pd.DataFrame) -> Dict[str, Any]:
    sub = df_en[(df_en["outstanding"] > 0)].sort_values(
        ["status", "days_overdue", "outstanding"], ascending=[True, False, False]
    )
    table = sub[["invoice_id", "supplier", "due_date", "status", "days_overdue", "outstanding"]].copy()
    return {"summary": f"{len(table)} cuentas por pagar abiertas", "table": table.to_dict(orient="records")}


# -----------------------------
# Agente ejecutor
# -----------------------------
class Agent(BaseAgent):
    name = "aaav_cxp"
    role = "operational"

    def handle(self, task, state: GlobalState) -> Dict[str, Any]:
        """
        Espera en payload:
          - period: "YYYY-MM"
          - path: opcional, ruta Excel (real time)
          - action: str en {"metrics","top_overdue","due_soon","supplier_balance","list_open"}
          - params: dict con parámetros de la acción (n, days, supplier, ...)
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
            base = _act_metrics(df, period, start, end, ref_date)  # incluye dpo top-level

            # Si solo pidieron métricas:
            if action == "metrics":
                return {"agent": self.name, **base}

            # Para acciones de lista, enriquecemos
            df_en = _enrich_df(df, ref_date)

            if action == "top_overdue":
                out = _act_top_overdue(df_en, n=params.get("n", 10))
            elif action == "due_soon":
                out = _act_due_soon(df_en, days=params.get("days", 7))
            elif action == "supplier_balance":
                supp = params.get("supplier")
                if not supp:
                    return {"agent": self.name, "error": "Falta 'supplier' en params"}
                out = _act_supplier_balance(df_en, supplier=supp)
            elif action == "list_open":
                out = _act_list_open(df_en)
            else:
                return {"agent": self.name, "error": f"Acción desconocida: {action}"}

            # Devolvemos métricas base + resultado de la acción + mirror DPO top-level
            return {
                "agent": self.name,
                "summary": f"CxP ejecutado: {action}",
                "data": base["data"],
                "dpo": base.get("dpo"),  # espejo top-level compatible con av_gerente
                "result": {"action": action, **out},
            }

        except Exception as e:
            return {
                "agent": self.name,
                "error": str(e),
                "needs": {"path": path, "required_cols": REQUIRED},
            }
