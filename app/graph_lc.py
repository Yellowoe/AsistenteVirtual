# app/graph_lc.py
from typing import Dict, Any, List
from app.state import GlobalState

from app.agents.av_gerente.logic import Agent as GerenteAgent
from app.agents.aav_contable.logic import Agent as ContableAgent
from app.agents.aaav_cxc.logic import Agent as CxcAgent
from app.agents.aaav_cxp.logic import Agent as CxpAgent

try:
    from app.agents.av_administrativo.logic import Agent as AdminAgent
except ModuleNotFoundError:
    AdminAgent = None


def _detect_intent(q: str) -> Dict[str, Any]:
    t = (q or "").lower()

    keywords_informe = [
        "informe financiero", "informe del mes", "reporte mensual",
        "reporte del mes", "informe de este mes", "resumen financiero",
    ]
    informe = any(kw in t for kw in keywords_informe)

    # 🔹 Nuevo: liquidez y cashflow
    liquidity_triggers = [
        "liquidez", "flujo de caja", "cash flow", "cashflow",
        "mejorar la liquidez", "mejorar liquidez", "caixa", "tesorería",
    ]
    liquidity = any(kw in t for kw in liquidity_triggers)

    cxc = informe or liquidity or any(kw in t for kw in ["cxc", "cuentas por cobrar", "cobro", "clientes por cobrar"])
    cxp = informe or liquidity or any(kw in t for kw in ["cxp", "cuentas por pagar", "pago", "proveedores"])

    return {"informe": informe, "cxc": cxc, "cxp": cxp, "reason": "heurística determinista es-ES"}


def run_query(question: str, period: str) -> Dict[str, Any]:
    state = GlobalState(period=period)
    intent = _detect_intent(question)
    trace: List[Dict[str, Any]] = []

    cxc = cxp = None
    if intent["cxc"]:
        cxc = CxcAgent().handle({"payload": {"period": period, "action": "metrics"}}, state=state)
        trace.append(cxc)

    if intent["cxp"]:
        cxp = CxpAgent().handle({"payload": {"period": period, "action": "metrics"}}, state=state)
        trace.append(cxp)

    contable_pack = None
    if cxc or cxp:
        contable = ContableAgent().handle({"payload": {"cxc_data": cxc, "cxp_data": cxp}}, state=state)
        trace.append(contable)
        contable_pack = contable.get("data")

    administrativo = None
    if contable_pack and AdminAgent is not None:
        try:
            administrativo = AdminAgent().handle({"payload": {"contable_pack": contable_pack}}, state=state)
        except Exception:
            administrativo = None

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
