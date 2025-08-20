from ..base import BaseAgent
from ...state import GlobalState
from typing import Dict, Any

class Agent(BaseAgent):
    name = "av_comercial"
    role = "management"

    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        # Aquí procesas 'task["payload"]' y usas self.llm si quieres
        payload = task.get("payload", {})
        return {'agent':'av_comercial','summary':'Campañas evaluadas','kpi':{'ROAS':3.2,'CAC':25,'LTV':180}}
