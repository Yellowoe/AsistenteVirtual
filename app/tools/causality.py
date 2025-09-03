# app/tools/causality.py
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _to_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def _extract_kpis_from_trace(trace: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """
    Busca KPIs en el trace con distintos formatos y los devuelve normalizados:
    { "DSO": float|None, "DPO": float|None, "CCC": float|None }
    """
    kpis: Dict[str, Optional[float]] = {"DSO": None, "DPO": None, "CCC": None}

    for res in trace or []:
        # 1) KPIs en data.kpi (formato de aaav_cxc/aaav_cxp/aav_contable)
        data = res.get("data") if isinstance(res, dict) else None
        if isinstance(data, dict):
            kpi_obj = data.get("kpi")
            if isinstance(kpi_obj, dict):
                for k, v in kpi_obj.items():
                    ku = str(k).strip().upper()
                    if ku in kpis:
                        kpis[ku] = _to_float(v)

        # 2) Métricas top-level en el propio result (compatibilidad)
        for k_src, k_dst in [("dso", "DSO"), ("dpo", "DPO"), ("ccc", "CCC")]:
            if isinstance(res, dict) and k_src in res and kpis[k_dst] is None:
                kpis[k_dst] = _to_float(res.get(k_src))

        # 3) Pack contable embebido como data (por si viene anidado distinto)
        if isinstance(data, dict) and "kpi" not in (data or {}):
            # algunos agentes devuelven todo el pack en data
            for k_src, k_dst in [("DSO", "DSO"), ("DPO", "DPO"), ("CCC", "CCC")]:
                if kpis[k_dst] is None and k_src in data:
                    kpis[k_dst] = _to_float(data.get(k_src))

    return kpis


def _normalize_aging(aging: Any) -> Dict[str, float]:
    """
    Recibe aging en cualquier forma razonable y devuelve un dict {bucket: monto_float}.
    Si viene una lista o algo raro, devuelve {}.
    """
    if isinstance(aging, dict):
        out: Dict[str, float] = {}
        for k, v in aging.items():
            out[str(k)] = _to_float(v) or 0.0
        return out
    return {}


def _long_tail_ratio(aging_cxc: Dict[str, float]) -> float:
    """
    Aproxima % de cartera vencida 'larga' (>=60 días).
    Busca claves con '60', '90', '>90', 'over', etc.
    """
    if not aging_cxc:
        return 0.0
    total = sum(aging_cxc.values()) or 0.0
    if total <= 0:
        return 0.0

    def is_long_bucket(name: str) -> bool:
        n = name.replace(" ", "").lower()
        return ("60" in n or "90" in n or ">90" in n or "over" in n or "mas90" in n or "+90" in n)

    long_sum = sum(v for k, v in aging_cxc.items() if is_long_bucket(str(k)))
    return (long_sum / total) if total > 0 else 0.0


def _near_due_ratio_ap(aging_cxp: Dict[str, float]) -> float:
    """
    % de cuentas por pagar próximas a vencer (0-30).
    Usa heurística simple por nombre del bucket.
    """
    if not aging_cxp:
        return 0.0
    total = sum(aging_cxp.values()) or 0.0
    if total <= 0:
        return 0.0

    def is_near_bucket(name: str) -> bool:
        n = name.replace(" ", "").lower()
        return ("0-30" in n) or ("0_30" in n) or ("<=30" in n) or ("30" in n and "-" in n)

    near = sum(v for k, v in aging_cxp.items() if is_near_bucket(str(k)))
    return (near / total) if total > 0 else 0.0


def causal_hypotheses(
    trace: List[Dict[str, Any]],
    aging_cxc: Optional[Dict[str, Any]] = None,
    aging_cxp: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Genera hipótesis causales 'clásicas' a partir de KPIs y aging.
    - tolerante a formatos
    - nunca lanza excepción por tipos
    """
    causes: List[str] = []

    kpi = _extract_kpis_from_trace(trace)
    dso = kpi.get("DSO")
    dpo = kpi.get("DPO")
    ccc = kpi.get("CCC")

    # Normaliza aging
    aging_cxc_n = _normalize_aging(aging_cxc or {})
    aging_cxp_n = _normalize_aging(aging_cxp or {})

    # Reglas simples
    if dso is not None and dso > 45:
        causes.append(f"DSO elevado ({dso:.1f}d > 45d) sugiere lentitud en cobranza / crédito laxo.")

    if dpo is not None and dpo < 40:
        causes.append(f"DPO bajo ({dpo:.1f}d < 40d) sugiere poca negociación con proveedores y salidas de caja tempranas.")

    if ccc is not None and ccc > 20:
        causes.append(f"CCC positivo y alto ({ccc:.1f}d > 20d) indica presión de ciclo de caja.")

    # Aging CxC — cola larga
    long_ratio = _long_tail_ratio(aging_cxc_n)
    if long_ratio >= 0.30:  # 30% o más en buckets >=60d
        pct = int(round(long_ratio * 100))
        causes.append(f"Concentración de cartera vencida en cola larga (≥60d ~{pct}%) presiona el DSO y la liquidez.")

    # Aging CxP — muchos por vencer pronto
    near_ratio_ap = _near_due_ratio_ap(aging_cxp_n)
    if near_ratio_ap >= 0.40:  # 40% o más por vencer pronto
        pct = int(round(near_ratio_ap * 100))
        causes.append(f"Alta proporción de CxP próximos a vencer (~{pct}%) podría tensionar pagos si no se renegocia.")

    # Relación DSO vs DPO
    if dso is not None and dpo is not None and (dso - dpo) > 10:
        causes.append("Desbalance entre DSO y DPO (cobras más tarde de lo que pagas) impacta el capital de trabajo.")

    # Fallback si no salió nada
    if not causes:
        causes.append("Datos insuficientes o sin señales claras; revisar detalle de aging y KPIs para concluir causas.")

    # Quita duplicados preservando orden
    seen = set()
    uniq: List[str] = []
    for c in causes:
        if c not in seen:
            uniq.append(c)
            seen.add(c)
    return uniq
