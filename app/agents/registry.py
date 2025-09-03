# app/agents/registry.py
from typing import Dict
from .base import BaseAgent

_REGISTRY: Dict[str, BaseAgent] = {}

def get_agent(name: str) -> BaseAgent:
    if name in _REGISTRY:
        return _REGISTRY[name]

    # CARGA PEREZOSA: importa solo cuando se pide
    if name == "aaav_cxc":
        from .aaav_cxc.logic import Agent as A
        _REGISTRY[name] = A()
    elif name == "aaav_cxp":
        from .aaav_cxp.logic import Agent as A
        _REGISTRY[name] = A()
    elif name == "aav_contable":
        from .aav_contable.logic import Agent as A
        _REGISTRY[name] = A()
    elif name == "av_administrativo":
        from .av_administrativo.logic import Agent as A
        _REGISTRY[name] = A()
    elif name == "av_gerente":
        from .av_gerente.logic import Agent as A
        _REGISTRY[name] = A()
    else:
        raise KeyError(f"Agente '{name}' no encontrado")

    return _REGISTRY[name]

AGENT_INFO = {
    "aaav_cxc": "Agente auxiliar de cuentas por cobrar",
    "aaav_cxp": "Agente auxiliar de cuentas por pagar",
    "aav_contable": "Agente de contabilidad",
    "av_administrativo": "Agente administrativo",
    "av_gerente": "Agente gerente (integrador y reportes ejecutivos)",
}
def list_agents():
    return list(AGENT_INFO.keys())