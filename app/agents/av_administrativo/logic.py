from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple

from ..base import BaseAgent
from ...state import GlobalState
from ...tools.calc_kpis import month_window


class Agent(BaseAgent):
    """AV_Administrativo

    Convierte el *pack contable* (consolidado por aav_contable) en hallazgos
    y **órdenes accionables** para las áreas (CxC, CxP, Operaciones, etc.).

    Entrada esperada (flexible):
      payload.contable_pack  -> objeto con { period, kpi{DSO,DPO,DIO,CCC}, balances{...} }
      o payload.contable     -> mismo objeto
      o payload.aav_contable -> salida completa del agente aav_contable

    Salida estructurada:
      {
        'summary': str,
        'hallazgos': [ {id, msg, kpi?, severity, evidence?} ],
        'orders': [ {id, title, owner, kpi?, priority, due, playbook, tags:[], depends_on:[] } ],
        'kpis_watch': [ 'DSO', 'DPO', 'CCC', ... ],
        '_meta': { 'ruleset_version': '1.0.0' }
      }

    Notas:
    - Fechas de vencimiento se fijan al último día del periodo (month_window).
    - Reglas y umbrales configurables por DEFAULTS.
    - No asume disponibilidad de inventarios/DIO, pero los usa si llegan.
    """

    name = "av_administrativo"
    role = "management"

    # ========================
    # Parámetros / Umbrales
    # ========================
    DEFAULTS = {
        "DSO_HIGH": 45.0,         # días
        "DPO_LOW": 40.0,          # días
        "CCC_HIGH": 20.0,         # días (si hay DIO; si no, se evalúa sobre DSO-DPO)
        "AR_AP_IMBALANCE_RATIO": 1.3,  # AR/AP outstanding ratio
        "MAX_ACTIONS": 8,
    }

    def _period_end(self, period: str) -> str:
        # month_window(period) -> (start_dt, end_dt, ref_date)
        _, end, _ = month_window(period)
        # end es datetime.date o datetime; lo devolvemos como YYYY-MM-DD
        return getattr(end, 'strftime', lambda fmt: str(end))("%Y-%m-%d")

    def _pick_pack(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Soporta múltiples llaves para comodidad
        pack = payload.get("contable_pack") or payload.get("contable")
        if not pack:
            # Si viene la salida completa del agente aav_contable
            ac = payload.get("aav_contable") or {}
            pack = (ac.get("data") or {})
        return pack or {}

    def _num(self, x: Any) -> Optional[float]:
        try:
            return float(x) if x is not None else None
        except Exception:
            return None

    def _findings(self, pack: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Genera hallazgos y órdenes a partir de KPIs y balances.
        Devuelve (hallazgos, orders_sugeridas)
        """
        rules = self.DEFAULTS
        period = pack.get("period", "")
        end_date = self._period_end(period) if period else None

        kpi = (pack.get("kpi") or {})
        dso = self._num(kpi.get("DSO"))
        dpo = self._num(kpi.get("DPO"))
        dio = self._num(kpi.get("DIO"))
        ccc = self._num(kpi.get("CCC"))

        bal = (pack.get("balances") or {})
        ar_total = self._num(bal.get("AR_outstanding"))
        ap_total = self._num(bal.get("AP_outstanding"))

        hallazgos: List[Dict[str, Any]] = []
        orders: List[Dict[str, Any]] = []

        # --- Regla 1: DSO alto ---
        if dso is not None and dso > rules["DSO_HIGH"]:
            hallazgos.append({
                "id": "DSO_HIGH",
                "msg": f"DSO alto ({dso:.1f}d > {rules['DSO_HIGH']:.0f}d): intensificar cobranza",
                "kpi": "DSO",
                "severity": "high",
                "evidence": {"DSO": dso},
            })
            orders.append({
                "id": "ORD_DSO_DUNNING",
                "title": "Campaña dunning top-10 clientes",
                "owner": "CxC",
                "kpi": "DSO",
                "priority": "P1",
                "due": end_date,
                "playbook": [
                    "Extraer top-10 por saldo y días vencidos",
                    "Enviar secuencia dunning T1/T2/T3",
                    "Ofrecer pronto pago con 2% descuento si aplica",
                    "Escalar cuentas >60d a gestión directa",
                ],
                "tags": ["cxc", "cobranzas", "cash"],
                "depends_on": [],
            })

        # --- Regla 2: DPO bajo ---
        if dpo is not None and dpo < rules["DPO_LOW"]:
            hallazgos.append({
                "id": "DPO_LOW",
                "msg": f"DPO bajo ({dpo:.1f}d < {rules['DPO_LOW']:.0f}d): negociar plazos con proveedores",
                "kpi": "DPO",
                "severity": "medium",
                "evidence": {"DPO": dpo},
            })
            orders.append({
                "id": "ORD_DPO_RENEG",
                "title": "Renegociar 3 proveedores clave",
                "owner": "CxP",
                "kpi": "DPO",
                "priority": "P2",
                "due": end_date,
                "playbook": [
                    "Identificar proveedores con mayor AP y rotación",
                    "Proponer +15 días de plazo a cambio de volumen/temprano pago",
                    "Implementar pagos quincenales escalonados",
                ],
                "tags": ["cxp", "negociación"],
                "depends_on": [],
            })

        # --- Regla 3: CCC elevado ---
        if ccc is not None and ccc > rules["CCC_HIGH"]:
            hallazgos.append({
                "id": "CCC_HIGH",
                "msg": f"CCC elevado ({ccc:.1f}d > {rules['CCC_HIGH']:.0f}d): presión de ciclo de caja",
                "kpi": "CCC",
                "severity": "high",
                "evidence": {"CCC": ccc, "DSO": dso, "DPO": dpo, "DIO": dio},
            })
            orders.append({
                "id": "ORD_CCC_EMERGE",
                "title": "Plan 30-60-90 de liquidez",
                "owner": "Finanzas",
                "kpi": "CCC",
                "priority": "P1",
                "due": end_date,
                "playbook": [
                    "Freeze gastos no esenciales (30d)",
                    "Acelerar cobros >60d (30d)",
                    "Renegociar AP >30d (60d)",
                    "Revisión de precios/márgenes por segmento (90d)",
                ],
                "tags": ["liquidez", "finanzas"],
                "depends_on": ["ORD_DSO_DUNNING", "ORD_DPO_RENEG"],
            })

        # --- Regla 4: Desbalance AR/AP ---
        if ar_total is not None and ap_total is not None and ap_total > 0:
            ratio = ar_total / ap_total
            if ratio > rules["AR_AP_IMBALANCE_RATIO"]:
                hallazgos.append({
                    "id": "AR_AP_IMBAL",
                    "msg": f"Desbalance AR/AP (ratio {ratio:.2f} > {rules['AR_AP_IMBALANCE_RATIO']:.2f})",
                    "severity": "medium",
                    "evidence": {"AR": ar_total, "AP": ap_total},
                })
                orders.append({
                    "id": "ORD_ARAP_SYNC",
                    "title": "Sync semanal CxC/CxP sobre flujos",
                    "owner": "Administración",
                    "priority": "P3",
                    "due": end_date,
                    "playbook": [
                        "Reconciliar aging AR/AP",
                        "Alinear calendario de cobranzas vs pagos",
                        "Aprobar excepciones por comité de caja",
                    ],
                    "tags": ["cash", "governance"],
                    "depends_on": [],
                })

        # Truncate número de órdenes si hay demasiadas
        if len(orders) > self.DEFAULTS["MAX_ACTIONS"]:
            orders = orders[: self.DEFAULTS["MAX_ACTIONS"]]

        return hallazgos, orders

    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        payload = task.get("payload", {}) or {}
        pack = self._pick_pack(payload)
        if not pack:
            return {"agent": self.name, "error": "Falta pack contable"}

        hallazgos, orders = self._findings(pack)

        summary = "Informe administrativo: " + (
            f"{len(hallazgos)} hallazgos, {len(orders)} órdenes"
        )

        return {
            "agent": self.name,
            "summary": summary,
            "hallazgos": hallazgos,
            "orders": orders,
            "kpis_watch": ["DSO", "DPO", "CCC"],
            "_meta": {"ruleset_version": "1.0.0"},
        }
