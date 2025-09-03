import json
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

# Intenta importar tu grafo real
RUN_QUERY_AVAILABLE = True
try:
    from app.graph_lc import run_query  # debe devolver un dict
except Exception:
    RUN_QUERY_AVAILABLE = False

# -----------------------------
# Config general
# -----------------------------
st.set_page_config(
    page_title="AV Gerente — Mini UI",
    page_icon="📊",
    layout="wide",
)

# Rutas para logs/exports
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------
# Helpers
# -----------------------------
def _strip_think(s: str) -> str:
    """Limpia bloques <think>…</think> o encabezados de razonamiento si llegan por error."""
    if not isinstance(s, str):
        return s
    s = re.sub(r"(?is)<\s*think\s*>.*?<\s*/\s*think\s*>", "", s)
    s = re.sub(r"(?is)^(thought|thinking|reasoning|chain\s*of\s*thought).*?(\n\n|$)", "", s)
    return s.strip()

def _mock_query(question: str, period: str) -> dict:
    return {
        "intent": "resumen_financiero",
        "gerente": {
            "executive_decision_bsc": {
                "resumen_ejecutivo": (
                    "Liquidez apretada por DSO alto respecto al umbral y CCC>20d. "
                    "Plan 30-60-90 y dunning top-10 sugeridos."
                ),
                "hallazgos": ["DSO por encima de 45d", "CCC elevado"],
                "riesgos": ["Riesgo de caja", "Incumplimiento de pagos"],
                "recomendaciones": [
                    "Campaña dunning (top-10)",
                    "Renegociar 3 proveedores",
                    "Freeze gastos no esenciales (30d)",
                ],
                "bsc": {
                    "finanzas": ["Mejorar conversión AR→cash", "Revisión márgenes"],
                    "clientes": ["Mantener SLA cobranzas sin afectar NPS"],
                    "procesos_internos": ["Calendario AR/AP semanal"],
                    "aprendizaje_crecimiento": ["Playbook de cobranza y negociación"],
                },
            }
        },
        "administrativo": {
            "hallazgos": [
                {
                    "id": "DSO_HIGH",
                    "msg": "DSO alto (51.4d > 45d): intensificar cobranza",
                    "kpi": "DSO",
                    "severity": "high",
                },
                {
                    "id": "CCC_HIGH",
                    "msg": "CCC elevado (23.2d > 20d): presión de ciclo de caja",
                    "kpi": "CCC",
                    "severity": "high",
                },
            ],
            "orders": [
                {
                    "id": "ORD_DSO_DUNNING",
                    "title": "Campaña dunning top-10 clientes",
                    "owner": "CxC",
                    "priority": "P1",
                    "due": f"{period}-30",
                },
                {
                    "id": "ORD_DPO_RENEG",
                    "title": "Renegociar 3 proveedores clave",
                    "owner": "CxP",
                    "priority": "P2",
                    "due": f"{period}-30",
                },
            ],
        },
        "trace": [
            {"agent": "aaav_cxc", "dso": 51.4},
            {"agent": "aaav_cxp", "dpo": 31.0},
        ],
    }

def _call_backend(question: str, period: str) -> dict:
    # Decide MOCK por toggle o por disponibilidad real del backend
    use_mock = st.session_state.get("use_mock", not RUN_QUERY_AVAILABLE)
    if use_mock or not RUN_QUERY_AVAILABLE or "run_query" not in globals():
        return _mock_query(question, period)
    # Llamada al grafo real con fallback seguro
    try:
        return run_query(question, period)
    except Exception as e:
        st.error("Fallo en backend. Usando MOCK.")
        st.exception(e)  # muestra stacktrace en la UI
        return _mock_query(question, period)

def _save_last_result(obj: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = EXPORT_DIR / f"result_{ts}.json"
    out.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.header("⚙️ Configuración")
backend_status = "✅ Disponible" if RUN_QUERY_AVAILABLE else "❌ No disponible"
st.sidebar.caption(f"Backend: {backend_status}")
st.sidebar.toggle(
    "Modo MOCK",
    key="use_mock",
    value=not RUN_QUERY_AVAILABLE,
    help="Genera una respuesta simulada si tu backend no está listo."
)
period = st.sidebar.text_input("Periodo (YYYY-MM)", value="2025-08")
show_trace = st.sidebar.checkbox("Ver trace crudo", value=False)

# -----------------------------
# Main
# -----------------------------
st.title("AV Gerente — Mini UI (Python)")
st.caption("Haz preguntas y visualiza el resumen ejecutivo, hallazgos y órdenes.")

question = st.text_area(
    "Pregunta",
    placeholder="¿Cómo cerramos el mes? ¿Qué acciones sugieres para mejorar la liquidez?",
    height=120,
)

col1, col2 = st.columns([1, 1], gap="large")
with col1:
    if st.button("Consultar", type="primary"):
        if not question.strip():
            st.warning("Escribe una pregunta.")
        else:
            try:
                with st.spinner("Consultando…"):
                    result = _call_backend(question.strip(), period.strip())
                st.session_state["last_result"] = result
                st.success("¡Listo!")
            except Exception as e:
                st.error(f"Error: {e}")
with col2:
    if st.button("Guardar último resultado"):
        res = st.session_state.get("last_result")
        if not res:
            st.warning("No hay resultado para guardar.")
        else:
            path = _save_last_result(res)
            st.success(f"Guardado en {path}")

st.divider()

result = st.session_state.get("last_result")
if not result:
    st.info("Realiza una consulta para ver resultados.")
else:
    gerente = result.get("gerente") or {}
    admin = result.get("administrativo") or result.get("av_administrativo") or {}

    # Resumen ejecutivo (BSC)
    with st.container(border=True):
        st.subheader("📄 Resumen ejecutivo (BSC)")
        exec_pack = gerente.get("executive_decision_bsc")
        if exec_pack is None:
            st.write("No se recibió un resumen ejecutivo estructurado.")
        elif isinstance(exec_pack, dict):
            st.json(exec_pack, expanded=False)
        else:
            # Limpieza defensiva por si viniera texto con razonamiento
            safe_text = _strip_think(str(exec_pack))
            try:
                parsed = json.loads(safe_text)
                st.json(parsed, expanded=False)
            except Exception:
                st.markdown(safe_text)

    # Hallazgos y órdenes
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("🧭 Hallazgos")
        findings = admin.get("hallazgos") or []
        if not findings:
            st.caption("Sin hallazgos.")
        else:
            for h in findings:
                with st.expander(h.get("msg", h.get("id", "Hallazgo")), expanded=False):
                    st.write({k: v for k, v in h.items() if k not in {"msg"}})
    with c2:
        st.subheader("🛠️ Órdenes")
        orders = admin.get("orders") or []
        if not orders:
            st.caption("Sin órdenes.")
        else:
            for o in orders:
                title = o.get("title", o.get("id", "Orden"))
                with st.expander(title, expanded=False):
                    st.write(o)

    # Intent & trace
    with st.expander("🔎 Intent & Trace", expanded=show_trace):
        st.write({"intent": result.get("intent")})
        st.json(result.get("trace") or result, expanded=False)

# -----------------------------
# Cómo ejecutar (nota visible)
# -----------------------------

