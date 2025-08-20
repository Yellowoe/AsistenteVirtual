from typing import Dict, Any
from .agents.registry import get_agent
from .state import GlobalState

class Router:
    def __init__(self, default_agent: str = "av_gerente"):
        self.default_agent = default_agent

    def dispatch(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        agent_name = task.get("agent", self.default_agent)
        agent = get_agent(agent_name)
        return agent.handle(task, state)
