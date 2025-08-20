from typing import Dict, Any
from ..state import GlobalState

class BaseAgent:
    name: str = "base"
    role: str = "generic"

    def __init__(self, llm=None):
        self.llm = llm

    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        raise NotImplementedError
