from dataclasses import dataclass, field
from typing import Any, Dict

@dataclass
class GlobalState:
    period: str = "2025-08"
    context: Dict[str, Any] = field(default_factory=dict)
