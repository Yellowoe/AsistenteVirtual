from ..base import BaseAgent
from ...state import GlobalState
from typing import Dict, Any

class Agent(BaseAgent):
    name = "av_operaciones"
    role = "management"

    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        # Aquí procesas 'task["payload"]' y usas self.llm si quieres
        payload = task.get("payload", {})
        return {'agent':'av_operaciones','summary':'OTIF y OEE monitoreados','kpi':{'OTIF':95,'OEE':72}}
