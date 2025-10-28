# app/agents/aaav_cxc/logic.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd
from dateutil import parser as dateparser

from ..base import BaseAgent
from ...state import GlobalState
from ...tools.calc_kpis import month_window
from ...tools.schema_validate import validate_with

from app.database import SessionLocal
from app.models import FacturaCXC, Entidad
from app.repo_finanzas_db import FinanzasRepoDB

SCHEMA = "app/schemas/aaav_cxc_schema.json"

# ---------------------------------------------------------------------
# Período
# ---------------------------------------------------------------------
@dataclass
class PeriodWindow:
    text: str
    start: pd.Timestamp
    end: pd.Timestamp

def _resolve_period(payload: Dict[str, Any], state: GlobalState) -> PeriodWindow:
    """
    Acepta:
      - payload["period_range"] dict con ISO start/end (preferido, del router)
      - payload["period"] en formato 'YYYY-MM'
      - state.period (dict del router)
    """
    pr = payload.get("period_range") or getattr(state, "period", None)
    if isinstance(pr, dict) and pr.get("start") and pr.get("end"):
        start = pd.Timestamp(dateparser.isoparse(pr["start"]))
        end   = pd.Timestamp(dateparser.isoparse(pr["end"]))
        text  = pr.get("text") or f"{start.year:04d}-{start.month:02d}"
        return PeriodWindow(text=text, start=start, end=end)

    p = payload.get("period") or getattr(state, "period_raw", None)
    if isinstance(p, str) and len(p) == 7 and p[4] == "-":
        s, e, _ = month_window(p)
        return PeriodWindow(text=p, start=s, end=e)

    # Fallback: mes actual (TZ del sistema)
    today = pd.Timestamp.today(tz="America/Costa_Rica")
    ym = today.strftime("%Y-%m")
    s, e, _ = month_window(ym)
    return PeriodWindow(text=ym, start=s, end=e)

# ---------------------------------------------------------------------
# Helpers DB (CXC)
# ---------------------------------------------------------------------
def _saldo_cxc(f: FacturaCXC) -> Decimal:
    # saldo = monto - monto_pagado
    return Decimal((f.monto or 0) - (f.monto_pagado or 0))

def _aging_and_totals_db(ref_date: date) -> Tuple[Dict[str, float], float, float]:
    """
    Devuelve:
      - aging SOLO vencido con llaves normalizadas: 0_30, 31_60, 61_90, 90_plus
      - total_por_cobrar (saldo abierto)
      - por_vencer (no vencido, incluye 'sin fecha')
    """
    db = SessionLocal()
    overdue = {
        "0_30": Decimal("0"),
        "31_60": Decimal("0"),
        "61_90": Decimal("0"),
        "90_plus": Decimal("0"),
    }
    current = Decimal("0")     # no vencido (<= 0 días)
    no_due = Decimal("0")      # sin fecha_limite
    try:
        for f in db.query(FacturaCXC):
            saldo = _saldo_cxc(f)
            if saldo <= 0:
                continue
            # FECHA DE VENCIMIENTO EN TU TABLA: fecha_limite
            if not f.fecha_limite:
                no_due += saldo
                continue
            days = (ref_date - f.fecha_limite.date()).days
            if days <= 0:
                current += saldo
            elif days <= 30:
                overdue["0_30"] += saldo
            elif days <= 60:
                overdue["31_60"] += saldo
            elif days <= 90:
                overdue["61_90"] += saldo
            else:
                overdue["90_plus"] += saldo

        total_por_cobrar = float(current + no_due + sum(overdue.values()))
        por_vencer = float(current + no_due)
        return ({k: float(v) for k, v in overdue.items()}, total_por_cobrar, por_vencer)
    finally:
        db.close()

def _list_top_overdue_db(limit_n: int, ref_date: date) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows: List[Dict[str, Any]] = []
        for f in db.query(FacturaCXC):
            saldo = float(_saldo_cxc(f))
            if saldo <= 0:
                continue
            days_over = 0
            if f.fecha_limite:
                days_over = max((ref_date - f.fecha_limite.date()).days, 0)
            if days_over <= 0:
                continue
            cliente = f.cliente.nombre_legal if getattr(f, "cliente", None) else str(getattr(f, "id_entidad_cliente", ""))
            rows.append({
                "invoice_id": f.numero_factura,
                "customer": cliente,
                "due_date": f.fecha_limite.date() if f.fecha_limite else None,
                "days_overdue": days_over,
                "outstanding": saldo,
            })
        rows.sort(key=lambda r: (r["days_overdue"], r["outstanding"]), reverse=True)
        return rows[: int(limit_n)]
    finally:
        db.close()

def _customer_balance_db(name_or_id: str, ref_date: date):
    target = str(name_or_id).strip()
    db = SessionLocal()
    try:
        cust = db.query(Entidad).filter(Entidad.nombre_legal.ilike(target)).first()
        cust_id = cust.id_entidad if cust else None
        if not cust_id:
            try:
                cust_id = int(target)
            except Exception:
                cust_id = None

        total = 0.0
        rows: List[Dict[str, Any]] = []
        q = db.query(FacturaCXC)
        if cust_id:
            q = q.filter(FacturaCXC.id_entidad_cliente == cust_id)

        for f in q:
            saldo = float(_saldo_cxc(f))
            if saldo <= 0:
                continue
            days_over = 0
            if f.fecha_limite:
                days_over = max((ref_date - f.fecha_limite.date()).days, 0)
            rows.append({
                "invoice_id": f.numero_factura,
                "issue_date": f.fecha_emision.date() if f.fecha_emision else None,
                "due_date": f.fecha_limite.date() if f.fecha_limite else None,
                "days_overdue": days_over,
                "outstanding": saldo,
            })
            total += saldo
        return total, rows
    finally:
        db.close()

def _list_open_db(ref_date: date) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows: List[Dict[str, Any]] = []
        for f in db.query(FacturaCXC):
            saldo = float(_saldo_cxc(f))
            if saldo <= 0:
                continue
            due = f.fecha_limite.date() if f.fecha_limite else None
            days_over = max((ref_date - due).days, 0) if due else 0
            status = "paid/zero"
            if saldo > 0 and days_over == 0 and due and (due - ref_date).days >= 0:
                status = "open_on_time"
            elif saldo > 0 and days_over > 0:
                status = "overdue"
            cliente = f.cliente.nombre_legal if getattr(f, "cliente", None) else str(getattr(f, "id_entidad_cliente", ""))
            rows.append({
                "invoice_id": f.numero_factura,
                "customer": cliente,
                "due_date": due,
                "status": status,
                "days_overdue": days_over,
                "outstanding": saldo,
            })
        rows.sort(key=lambda r: (r["status"], -r["days_overdue"], -r["outstanding"]))
        return rows
    finally:
        db.close()

# ---------------------------------------------------------------------
# Agente CxC normalizado
# ---------------------------------------------------------------------
class Agent(BaseAgent):
    name = "aaav_cxc"
    role = "operational"

    def handle(self, task, state: GlobalState) -> Dict[str, Any]:
        """
        Espera en payload:
          - period_range: {text, start, end, granularity, tz}  (preferido)
          - period: "YYYY-MM"                                   (fallback)
          - action: {"metrics","top_overdue","customer_balance","list_open"}
          - params: {n, customer}
        """
        payload = task.get("payload", {}) or {}
        action: str = (payload.get("action") or "metrics").strip()
        params: Dict[str, Any] = payload.get("params", {}) or {}

        # 1) Período unificado
        win = _resolve_period(payload, state)
        ref_date = win.end.date()

        # 2) KPI base DSO (si tu repo lo tiene)
        repo = FinanzasRepoDB()
        try:
            kpi_dso = repo.dso(win.start.year, win.start.month)
        except Exception:
            kpi_dso = None

        # 3) Aging SOLO vencido + totales desde BD
        try:
            aging_overdue, total_por_cobrar, por_vencer = _aging_and_totals_db(ref_date)
        except Exception as e:
            return {"agent": self.name, "error": f"Error leyendo CxC DB: {e}"}

        # 4) Paquete normalizado para UI/Contable
        data_norm = {
            "period": win.text,
            "kpi": {"DSO": kpi_dso},
            "aging": {
                "0_30": float(aging_overdue.get("0_30", 0.0)),
                "31_60": float(aging_overdue.get("31_60", 0.0)),
                "61_90": float(aging_overdue.get("61_90", 0.0)),
                "90_plus": float(aging_overdue.get("90_plus", 0.0)),
            },
            "total_por_cobrar": float(total_por_cobrar),
            "por_vencer": float(por_vencer),
            "current": float(por_vencer),  # alias
        }

        # 5) Validación (no bloqueante)
        try:
            validate_with(SCHEMA, data_norm)
        except Exception:
            pass

        # 6) Acciones
        if action == "metrics":
            return {
                "agent": self.name,
                "summary": "CxC calculado (DB)",
                "data": data_norm,
                "dso": kpi_dso,
            }

        if action == "top_overdue":
            table = _list_top_overdue_db(params.get("n", 10), ref_date)
            return {
                "agent": self.name,
                "summary": "Top facturas por cobrar vencidas (más urgentes)",
                "data": data_norm,
                "dso": kpi_dso,
                "result": {"action": action, "table": table},
            }

        if action == "customer_balance":
            cust = params.get("customer")
            if not cust:
                return {"agent": self.name, "error": "Falta 'customer' en params"}
            total, table = _customer_balance_db(cust, ref_date)
            return {
                "agent": self.name,
                "summary": f"Saldo pendiente con el cliente '{cust}': {total:.2f}",
                "data": data_norm,
                "dso": kpi_dso,
                "result": {"action": action, "total_outstanding": total, "table": table},
            }

        if action == "list_open":
            table = _list_open_db(ref_date)
            return {
                "agent": self.name,
                "summary": "Cuentas por cobrar abiertas",
                "data": data_norm,
                "dso": kpi_dso,
                "result": {"action": action, "table": table},
            }

        # Acción no reconocida → métrica base
        return {
            "agent": self.name,
            "summary": "CxC calculado (DB)",
            "data": data_norm,
            "dso": kpi_dso,
        }
