# app/graph_lc.py
from typing import Dict, Any, List

# Estado global
from app.state import GlobalState

# =========================
# IMPORTS (todas a logic.py)
# =========================
from app.agents.av_gerente.logic import Agent as GerenteAgent
from app.agents.aav_contable.logic import Agent as ContableAgent
from app.agents.aaav_cxc.logic import Agent as CxcAgent
from app.agents.aaav_cxp.logic import Agent as CxpAgent

# Administrativo (si lo tienes en app/agents/av_administrativo/logic.py)
try:
    from app.agents.av_administrativo.logic import Agent as AdminAgent
except ModuleNotFoundError:
    AdminAgent = None  # si no existe, saltamos ese paso


def _detect_intent(q: str) -> Dict[str, Any]:
    t = (q or "").lower()
    informe = any(
        kw in t
        for kw in [
            "informe financiero",
            "informe del mes",
            "reporte mensual",
            "reporte del mes",
            "informe de este mes",
            "resumen financiero",
        ]
    )
    cxc = informe or any(kw in t for kw in ["cxc", "cuentas por cobrar", "cobro", "clientes por cobrar"])
    cxp = informe or any(kw in t for kw in ["cxp", "cuentas por pagar", "pago", "proveedores"])
    return {"informe": informe, "cxc": cxc, "cxp": cxp, "reason": "heurística determinista es-ES"}


def run_query(question: str, period: str) -> Dict[str, Any]:
    # Crear y pasar GlobalState a TODOS los agentes
    state = GlobalState(period=period)

    intent = _detect_intent(question)
    trace: List[Dict[str, Any]] = []

    # 1) Subagentes operativos (metrics para aging + KPIs)
    cxc = cxp = None
    if intent["cxc"]:
        cxc = CxcAgent().handle({"payload": {"period": period, "action": "metrics"}}, state=state)
        trace.append(cxc)

    if intent["cxp"]:
        cxp = CxpAgent().handle({"payload": {"period": period, "action": "metrics"}}, state=state)
        trace.append(cxp)

    # 2) Consolidación contable si hay CxC o CxP
    contable_pack = None
    if cxc or cxp:
        contable = ContableAgent().handle({"payload": {"cxc_data": cxc, "cxp_data": cxp}}, state=state)
        trace.append(contable)
        contable_pack = contable.get("data")

    # 3) Administrativo (hallazgos/órdenes) si hay pack y el agente existe
    administrativo = None
    if contable_pack and AdminAgent is not None:
        try:
            administrativo = AdminAgent().handle({"payload": {"contable_pack": contable_pack}}, state=state)
        except Exception:
            administrativo = None  # no bloquees el flujo si este paso falla

    # 4) Informe ejecutivo del gerente
    gerente = GerenteAgent().handle(
        {"payload": {"question": question, "period": period, "trace": trace}},
        state=state,
    )

    return {
        "intent": intent,
        "trace": trace,
        "administrativo": administrativo,
        "gerente": gerente,
    }
