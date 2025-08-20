from ..base import BaseAgent
from ...state import GlobalState
from typing import Dict, Any

class Agent(BaseAgent):
    name = "aav_contable"
    role = "consolidation"

    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        # Espera entradas previas de CxC y CxP (pueden venir en task['payload'] o del flujo orquestado)
        cxc = task.get("payload", {}).get("cxc_data")
        cxp = task.get("payload", {}).get("cxp_data")

        if not cxc or not cxp:
            return {"agent": self.name, "error": "Faltan datos CxC/CxP para consolidar"}

        period = cxc["period"]
        dso = cxc["kpi"].get("DSO")
        dpo = cxp["kpi"].get("DPO")
        # DIO no calculado aquí; se puede agregar luego con Inventarios
        ccc = (dso or 0) - (dpo or 0)  # simplificado

        pack = {
            "period": period,
            "er": {}, "esf": {},
            "kpi": {"DSO": dso, "DPO": dpo, "CCC": ccc},
            "checks": ["Base contable mínima generada"]
        }
        return {"agent": self.name, "summary": "Pack contable emitido", "data": pack}
