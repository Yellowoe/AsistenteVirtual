# app/graph_lc.py
from __future__ import annotations
from typing import Dict, Any, Optional
from app.state import GlobalState
from app.router import Router

def run_query(question: str, period: Optional[str] = None) -> Dict[str, Any]:
    state = GlobalState()
    state.period_raw = period  # para que el Router pueda leer el YYYY-MM de la sidebar
    router = Router()
    return router.dispatch({"payload": {"question": question, "period": period}}, state)
