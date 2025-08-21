from ..base import BaseAgent
from ...state import GlobalState
from typing import Dict, Any

class Agent(BaseAgent):
    name = "av_administrativo"
    role = "management"

    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        pack = task.get("payload", {}).get("contable_pack")
        if not pack:
            return {"agent": self.name, "error": "Falta pack contable"}

        kpi = pack.get("kpi", {})
        hallazgos = []
        if (kpi.get("DSO") or 0) > 45:
            hallazgos.append("DSO alto: intensificar cobranza")
        if (kpi.get("DPO") or 0) < 40:
            hallazgos.append("DPO bajo: negociar plazos con proveedores")

        orders = []
        if "DSO alto: intensificar cobranza" in hallazgos:
            orders.append({"title":"Campaña dunning top-10 clientes","owner":"CxC","kpi":"DSO","due":f"{state.period}-30"})
        if "DPO bajo: negociar plazos con proveedores" in hallazgos:
            orders.append({"title":"Renegociar 3 proveedores clave","owner":"CxP","kpi":"DPO","due":f"{state.period}-30"})

        return {"agent": self.name, "summary": "Informe ejecutivo", "hallazgos": hallazgos, "orders": orders}
