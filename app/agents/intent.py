from typing import Any, Dict
import json
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from app.lc_llm import get_chat_model

try:
    from app.utils.text import strip_think
except Exception:

    def strip_think(text: str) -> str:
        return (text or "").replace("<think>", "").replace("</think>", "").strip()


class Intent(BaseModel):
    cxc: bool = Field(False)
    cxp: bool = Field(False)
    informe: bool = Field(False)
    reason: str = Field("")


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, (list, dict)):
        return len(value) > 0
    s = str(value).strip().lower()
    return s in {"true", "sí", "si", "yes", "y", "1"}


def _extract_json(text: str) -> Dict[str, Any]:
    t = strip_think(text or "")
    try:
        return json.loads(t)
    except Exception:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(t[start : end + 1])
        except Exception:
            pass
    return {}


def route_intent(question: str) -> Intent:
    q_low = (question or "").lower().strip()

    # 1) Heurística rápida (no bloquea)
    cxc = any(k in q_low for k in ["cxc", "cobrar", "clientes", "factura", "facturas", "dso", "por cobrar", "cuentas por cobrar"])
    cxp = any(k in q_low for k in ["cxp", "proveedor", "proveedores", "pago", "pagos", "dpo", "por pagar", "cuentas por pagar"])
    informe = any(k in q_low for k in ["informe ejecutivo", "bsc", "balanced scorecard", "resumen gerencial", "informe"])

    # Si ya hay señales claras, devuelve sin LLM
    if cxc or cxp or informe:
        reason = "Heurística por palabras clave"
        return Intent(cxc=cxc, cxp=cxp, informe=informe, reason=reason)

    # 2) Si es ambiguo, entonces pregunta al LLM (esto sí puede tardar)
    llm = get_chat_model()
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """Eres un router financiero. Debes clasificar la pregunta en tres flags booleanos: cxc, cxp, informe.
- cxc = true si la pregunta requiere Cuentas por Cobrar (DSO, aging, facturas)
- cxp = true si requiere Cuentas por Pagar (DPO, aging, pagos)
- informe = true si pide 'informe ejecutivo', 'BSC', 'resumen gerencial', etc.
Si la pregunta es ambigua, activa cxc=true y cxp=true.
RESPONDE SOLO un JSON con EXACTAMENTE estas llaves: cxc, cxp, informe, reason.
No agregues campos adicionales ni texto extra.

Ejemplo 1:
Pregunta: ¿Cómo está el DSO y el aging de clientes?
{{"cxc": true, "cxp": false, "informe": false, "reason": "Pregunta sobre CxC"}}

Ejemplo 2:
Pregunta: Dame un informe ejecutivo con BSC para agosto.
{{"cxc": true, "cxp": true, "informe": true, "reason": "Informe BSC requiere KPIs CxC y CxP"}}

Ejemplo 3:
Pregunta: ¿Qué DPO tenemos este mes?
{{"cxc": false, "cxp": true, "informe": false, "reason": "Pregunta sobre CxP"}}
"""
        ),
        (
            "human",
            """Pregunta: {question}

Devuelve SOLO el JSON final (sin comentarios, sin texto extra)."""
        ),
    ])

    try:
        msg = (prompt | llm).invoke({"question": question})
        content = getattr(msg, "content", str(msg))
        obj = _extract_json(content)
        cxc = _coerce_bool(obj.get("cxc"))
        cxp = _coerce_bool(obj.get("cxp"))
        informe = _coerce_bool(obj.get("informe"))
        reason = str(obj.get("reason") or "").strip()
        # Fallback mínimo si el LLM no devolvió nada útil
        if not (cxc or cxp or informe):
            cxc = True; cxp = True; reason = "Fallback ambiguo: ambos"
        return Intent(cxc=cxc, cxp=cxp, informe=informe, reason=reason)
    except Exception as e:
        # En caso de error del LLM, no bloquees: usa heurística por defecto
        return Intent(cxc=True, cxp=True, informe=False, reason=f"Fallback por error LLM: {e}")

