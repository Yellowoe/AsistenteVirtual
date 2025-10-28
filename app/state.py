# app/state.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from datetime import datetime
from zoneinfo import ZoneInfo

CR_TZ = ZoneInfo("America/Costa_Rica")

def _now_cr() -> datetime:
    return datetime.now(CR_TZ)

def _default_period() -> Dict[str, Any]:
    """Mes actual en TZ CR como fallback determinista."""
    today = _now_cr()
    start = datetime(today.year, today.month, 1, 0, 0, 0, tzinfo=CR_TZ)
    # fin de mes (cómodo sin calendar): ir a mes siguiente día 1 y restar 1s
    if today.month == 12:
        next_month = datetime(today.year + 1, 1, 1, 0, 0, 0, tzinfo=CR_TZ)
    else:
        next_month = datetime(today.year, today.month + 1, 1, 0, 0, 0, tzinfo=CR_TZ)
    end = (next_month - timedelta(seconds=1))
    return {
        "text": "auto: mes actual",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "granularity": "month",
        "source": "default",
        "tz": "America/Costa_Rica",
    }

from datetime import timedelta  # import tardío para usar arriba

@dataclass
class GlobalState:
    """
    Estado global compartido por agentes.
    - period: dict unificado {text, start, end, granularity, source, tz}
    - period_raw: string crudo (e.g., 'YYYY-MM' desde la sidebar) para trazabilidad
    - context: bolsa para compartir artefactos entre agentes
    - trace: acumulador de eventos/resultados
    """
    period: Dict[str, Any] = field(default_factory=_default_period)
    period_raw: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # ---- Utilidades de período (con tolerancia a valores faltantes) ----
    def period_start_dt(self) -> datetime:
        try:
            return datetime.fromisoformat(self.period["start"]).astimezone(CR_TZ)
        except Exception:
            return _now_cr().replace(hour=0, minute=0, second=0, microsecond=0)

    def period_end_dt(self) -> datetime:
        try:
            return datetime.fromisoformat(self.period["end"]).astimezone(CR_TZ)
        except Exception:
            return _now_cr().replace(hour=23, minute=59, second=59, microsecond=0)

    def period_text(self) -> str:
        return (self.period or {}).get("text", "")

    def period_tz(self) -> str:
        return (self.period or {}).get("tz", "America/Costa_Rica")

    # ---- Compatibilidad hacia atrás (si algún agente aún espera str) ----
    def period_yyyymm(self) -> str:
        """
        Devuelve 'YYYY-MM' para agentes legacy que aún reciban un string.
        Toma la fecha de inicio del período.
        """
        dt = self.period_start_dt()
        return f"{dt.year:04d}-{dt.month:02d}"

    # ---- Gestión de traza/errores ----
    def add_trace(self, item: Dict[str, Any]) -> None:
        self.trace.append(item)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    # ---- Helper general ----
    def set_period(self, period_dict: Dict[str, Any]) -> None:
        """
        Establece un período unificado ya resuelto (dict con start/end ISO).
        No hace parsing; el parsing se hace en el router/graph antes.
        """
        # merge defensivo para no perder llaves esperadas por la UI
        base = _default_period()
        base.update(period_dict or {})
        self.period = base
