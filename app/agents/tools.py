# app/agents/tools.py
from typing import Optional, Dict, Any
from langchain_core.tools import tool
from .registry import get_agent
from ..state import GlobalState

@tool("run_cxc")
def run_cxc(period: Optional[str] = None) -> Dict[str, Any]:
    """Ejecuta el agente CxC y devuelve KPIs, aging e incidentes."""
    state = GlobalState()
    return get_agent("aaav_cxc").handle({"payload": {"period": period}}, state)

@tool("run_cxp")
def run_cxp(period: Optional[str] = None) -> Dict[str, Any]:
    """Ejecuta el agente CxP y devuelve KPIs y aging."""
    state = GlobalState()
    return get_agent("aaav_cxp").handle({"payload": {"period": period}}, state)

@tool("run_contable")
def run_contable(period: Optional[str] = None,
                 cxc_data: Optional[Dict[str, Any]] = None,
                 cxp_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Calcula pack contable (CCC, KPIs) a partir de CxC/CxP."""
    state = GlobalState()
    return get_agent("aav_contable").handle({
        "payload": {"period": period, "cxc_data": cxc_data, "cxp_data": cxp_data}
    }, state)
