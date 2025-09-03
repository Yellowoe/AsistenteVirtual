from __future__ import annotations

from typing import Dict, Any, Optional, List, Tuple

from ..base import BaseAgent
from ...state import GlobalState

# (Opcional) Si agregas esquemas más adelante
# from ...tools.schema_validate import validate_with
# SCHEMA = "app/schemas/aav_contable_schema.json"


class Agent(BaseAgent):
    """Agente Contable (Consolidación)

    Integra salidas de CxC (aaav_cxc), CxP (aaav_cxp) y opcionalmente Inventarios (aaav_inv)
    para producir un *pack contable* con KPIs (DSO/DPO/DIO/CCC) y resúmenes útiles.

    Compatibilidad:
    - Soporta inputs en `task.payload` (cxc_data/cxp_data/inv_data) tanto en forma de
      *objeto `data`* como en *objeto completo de agente* (con llaves top-level `dso`/`dpo` y `data.kpi`).
    - Emite mirrors top-level: `dso`, `dpo`, `dio`, `ccc` para uso directo por `av_gerente`.
    - Devuelve `summary` y `data` estructurada apta para UI.
    """

    name = "aav_contable"
    role = "consolidation"

    # ==========================
    # Utilidades privadas
    # ==========================
    def _get_period(self, *candidates: Optional[str]) -> str:
        for p in candidates:
            if isinstance(p, str) and p:
                return p
        return ""

    def _extract_kpi(self, blob: Dict[str, Any], key: str) -> Optional[float]:
        """Busca primero espejo top-level (ej. `dso`) y luego en `data.kpi[key]` (ej. `DSO`)."""
        # Mirror top-level
        if key.lower() in blob:
            try:
                return float(blob[key.lower()])
            except (ValueError, TypeError):
                pass
        # Dentro de data.kpi
        data = blob.get("data") or blob
        kpi = (data or {}).get("kpi") or {}
        if key in kpi:
            try:
                return float(kpi[key])
            except (ValueError, TypeError):
                return None
        return None

    def _extract_aging_total(self, blob: Dict[str, Any]) -> Optional[float]:
        data = blob.get("data") or blob
        aging = (data or {}).get("aging") or {}
        # Intenta claves típicas
        for k in ("total", "outstanding_total", "outstanding", "balance"):
            if k in aging:
                try:
                    return float(aging[k])
                except (ValueError, TypeError):
                    pass
        # Si aging es dict de buckets {"0-30": x, "31-60": y, ...}
        if isinstance(aging, dict) and aging:
            try:
                return float(sum(float(v) for v in aging.values() if isinstance(v, (int, float))))
            except Exception:
                return None
        return None

    # ==========================
    # Manejo principal
    # ==========================
    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        payload = task.get("payload", {}) or {}

        # Permite dos formatos: datos crudos (data) o objetos completos del agente
        cxc_in = payload.get("cxc_data") or payload.get("cxc") or {}
        cxp_in = payload.get("cxp_data") or payload.get("cxp") or {}
        inv_in = payload.get("inv_data") or payload.get("inventories") or {}

        if not cxc_in or not cxp_in:
            return {"agent": self.name, "error": "Faltan datos CxC/CxP para consolidar"}

        # Periodo (preferimos el de CxC; si no, el de CxP)
        period = self._get_period(
            (cxc_in.get("data") or {}).get("period"),
            (cxp_in.get("data") or {}).get("period"),
            cxc_in.get("period"),
            cxp_in.get("period"),
            state.period,
        )

        # KPIs CxC / CxP / Inventarios
        dso = self._extract_kpi(cxc_in, "DSO")
        dpo = self._extract_kpi(cxp_in, "DPO")
        dio = self._extract_kpi(inv_in, "DIO")  # opcional (si llega desde aaav_inv)

        # CCC: si hay DIO, usa fórmula completa; si no, usa simplificada
        ccc = None
        try:
            if dso is not None and dpo is not None and dio is not None:
                ccc = float(dso) + float(dio) - float(dpo)
            elif dso is not None and dpo is not None:
                ccc = float(dso) - float(dpo)
        except Exception:
            ccc = None

        # Saldos totales (si disponibilidad en `aging`)
        ar_total = self._extract_aging_total(cxc_in)  # cuentas por cobrar
        ap_total = self._extract_aging_total(cxp_in)  # cuentas por pagar

        # Paquete contable consolidado
        pack = {
            "period": period,
            "kpi": {
                "DSO": dso,
                "DPO": dpo,
                "DIO": dio,
                "CCC": ccc,
            },
            "balances": {
                "AR_outstanding": ar_total,
                "AP_outstanding": ap_total,
                # Net Working Capital aproximado (si hay datos)
                "NWC_proxy": (ar_total - ap_total) if (ar_total is not None and ap_total is not None) else None,
            },
            # Espacio para estados financieros (rellenar desde otros agentes/fuentes)
            "er": {},   # Estado de Resultados
            "esf": {},  # Estado de Situación Financiera
            "checks": [
                "Base contable consolidada a partir de CxC/CxP",
                "KPIs consistentes con mirrors top-level",
            ],
        }

        # (Opcional) validación de esquema
        # validate_with(SCHEMA, pack)

        # Salida con mirrors top-level + summary
        out = {
            "agent": self.name,
            "summary": "Pack contable consolidado (CxC/CxP" + ("/Inventarios" if dio is not None else "") + ")",
            "data": pack,
            # Mirrors para consumo directo por av_gerente
            "dso": dso,
            "dpo": dpo,
            "ccc": ccc,
        }

        # Si recibimos DIO, también lo exponemos como mirror (aunque av_gerente hoy no lo usa directo)
        if dio is not None:
            out["dio"] = dio

        return out
