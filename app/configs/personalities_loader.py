# app/config/personalities_loader.py
from __future__ import annotations
from typing import Dict, Any, List
import yaml
import re
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "agents_personalities.yaml"

def load_personalities(path: Path | None = None) -> Dict[str, Any]:
    p = path or DEFAULT_PATH
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def build_keyword_index(cfg: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """
    Devuelve { agent_name: { keyword: weight } }
    Sugerencias: ajusta pesos según tu dominio.
    """
    # Semillas base por agente
    base = {
        "aaav_cxc": {
            "cxc": 2.0, "cuentas por cobrar": 2.0, "cliente": 1.5,
            "morosidad": 1.5, "dso": 2.0, "aging cxc": 1.5, "vencidas cxc": 1.5,
            "factura cliente": 1.0, "cobro": 1.0, "cartera": 1.0,
        },
        "aaav_cxp": {
            "cxp": 2.0, "cuentas por pagar": 2.0, "proveedor": 1.5,
            "dpo": 2.0, "aging cxp": 1.5, "vencidas cxp": 1.5,
            "pago": 1.0, "orden de compra": 1.0, "oc": 1.0,
        },
        "aav_contable": {
            "estado financiero": 2.0, "estados financieros": 2.0, "balance": 1.5,
            "er": 1.5, "esf": 1.5, "cierre": 1.5, "ccc": 2.0, "ebitda": 1.5, "margen": 1.5
        },
        "av_administrativo": {
            "resumen": 1.0, "informe": 1.0, "ejecutivo": 1.0, "bsc": 1.5,
            "hallazgos": 1.0, "recomendaciones": 1.0, "decisiones": 1.0
        },
    }
    # Palabras transversales que intensifican señales
    transversal = {
        "liquidez": 1.0, "flujo de caja": 1.0, "cash flow": 1.0, "cashflow": 1.0, "tesorería": 1.0,
        "análisis financiero": 0.5, "analisis financiero": 0.5, "reporte": 0.5, "resumen financiero": 0.5
    }
    # Puedes enriquecer desde personalities.yaml si incluyes “kpi_library” o “rules”
    # (ej.: mapear KPIs a agentes con +0.5 cada uno)
    kpi_map = {
        "DSO": "aaav_cxc", "DPO": "aaav_cxp", "CCC": "aav_contable", "EBITDA": "aav_contable", "Margen": "aav_contable"
    }
    for kpi, agent in kpi_map.items():
        base.setdefault(agent, {})[kpi.lower()] = base.get(agent, {}).get(kpi.lower(), 0.0) + 0.5

    # inyecta transversal a todos
    for agent in base:
        for k, w in transversal.items():
            base[agent][k] = base[agent].get(k, 0.0) + w

    # normaliza claves
    norm = {}
    for agent, kws in base.items():
        norm[agent] = {re.sub(r"\s+", " ", k.strip().lower()): float(w) for k, w in kws.items()}
    return norm
