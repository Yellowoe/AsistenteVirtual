from dotenv import load_dotenv
load_dotenv()

# --- FIX de imports cuando el script vive dentro de app/ ---
import sys
import pathlib
FILE_PATH = pathlib.Path(__file__).resolve()
ROOT = FILE_PATH.parent              # .../AsistenteVirtual/app
PROJECT_ROOT = ROOT.parent           # .../AsistenteVirtual
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# -----------------------------------------------------------

import json
import re
from datetime import datetime
from pathlib import Path

import streamlit as st
import pandas as pd  # <- NUEVO: para tablas / bar_chart

# -----------------------------
# Asegura que 'app/' sea importable desde la raíz
# -----------------------------
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# -----------------------------
# Intenta importar tu grafo real y captura el error
# -----------------------------
RUN_QUERY_AVAILABLE = True
IMPORT_ERROR = None
try:
    from app.graph_lc import run_query  # debe exponer run_query(question: str, period: Optional[str])
except Exception as e:
    RUN_QUERY_AVAILABLE = False
    IMPORT_ERROR = e

# -----------------------------
# Config general
# -----------------------------
st.set_page_config(
    page_title="Agente Virtual",
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
        "intent": {"informe": True, "cxc": True, "cxp": True, "reason": "mock"},
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
                # KPIs para que las cards puedan leer de aquí también
                "kpis": {"DSO": 51.4, "DPO": 31.0, "CCC": 20.4},
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
            {"agent": "aaav_cxc",
             "summary": "CxC calculado (MOCK)",
             "data": {
                 "period": period,
                 "kpi": {"DSO": 51.4},
                 "aging": {"0_30": 12000, "31_60": 3500, "61_90": 0, "90_plus": 0},
                 "total_por_cobrar": 120000,
                 "por_vencer": 104500
             }},
            {"agent": "aaav_cxp",
             "summary": "CxP calculado (MOCK)",
             "data": {
                 "period": period,
                 "kpi": {"DPO": 31.0},
                 "aging": {"0_30": 9000, "31_60": 2000, "61_90": 0, "90_plus": 0},
                 "total_por_pagar": 80000,
                 "por_vencer": 69000
             }},
        ],
        "metrics": {"dso": 51.4, "dpo": 31.0, "ccc": 20.4, "cash": None},
        "_meta": {
            "period_resolved": {
                "text": period,
                "start": f"{period}-01T00:00:00-06:00",
                "end": f"{period}-28T23:59:59-06:00",
                "granularity": "month",
                "source": "mock",
                "tz": "America/Costa_Rica",
            },
            "router_sequence": ["aaav_cxc", "aaav_cxp", "aav_contable", "av_gerente"],
        }
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

# ====== Helpers UI de datos (nuevos) ======
def _fmt_days(v):
    try:
        return f"{float(v):.1f} d"
    except Exception:
        return "N/D"

def _norm_aging(aging: dict | None) -> dict:
    aging = aging or {}
    return {
        "0-30": float(aging.get("0_30") or aging.get("1-30") or 0),
        "31-60": float(aging.get("31_60") or aging.get("31-60") or 0),
        "61-90": float(aging.get("61_90") or aging.get("61-90") or 0),
        "90+": float(aging.get("90_plus") or aging.get("+90") or 0),
    }

def _get_agent_data(result: dict, agent_name: str) -> dict:
    for r in (result.get("trace") or []):
        if r.get("agent") == agent_name:
            return (r.get("data") or {})
    return {}

def _get_aging_from_result(result: dict, agent_name: str) -> dict:
    return _norm_aging(_get_agent_data(result, agent_name).get("aging"))

def _get_totals(result: dict, agent_name: str) -> dict:
    d = _get_agent_data(result, agent_name)
    aging_norm = _norm_aging(d.get("aging") or {})
    vencido = sum(aging_norm.values())
    total = float(d.get("total") or d.get("total_por_cobrar") or d.get("total_por_pagar") or 0)
    por_vencer = float(d.get("por_vencer") or 0)
    return {"Total": total, "Por vencer": por_vencer, "Vencido": vencido}

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.header("⚙️ Configuración")
backend_status = "✅ Disponible" if RUN_QUERY_AVAILABLE else "❌ No disponible"
st.sidebar.caption(f"Backend: {backend_status}")

# Si el backend NO está disponible, muestra el trace real del import
if not RUN_QUERY_AVAILABLE and IMPORT_ERROR is not None:
    st.sidebar.error("Backend no disponible (falló el import de run_query).")
    with st.sidebar:
        st.exception(IMPORT_ERROR)

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
    # -------------------------
    # Período resuelto (si viene desde el backend)
    # -------------------------
    with st.container(border=True):
        st.subheader("🗓️ Período resuelto")
        meta_period = (result.get("_meta") or {}).get("period_resolved")
        if not meta_period:
            # intenta hallar en trace
            trace = result.get("trace") or []
            meta_period = None
            for item in trace:
                p = (item.get("payload") or {}).get("period") if isinstance(item, dict) else None
                if p:
                    meta_period = p; break
        if meta_period:
            st.json(meta_period, expanded=False)
        else:
            st.caption("El backend no devolvió información del período.")

    # -------------------------
    # Banner de estado del informe (con/sin datos)
    # -------------------------
    metrics = (result or {}).get("metrics") or {}
    has_core = any([metrics.get("dso"), metrics.get("dpo"), metrics.get("ccc")])
    if has_core:
        st.success("✅ Informe generado: análisis con datos suficientes (DSO/DPO/CCC presentes).")
    else:
        st.warning("⚠️ Informe generado: sin datos suficientes. "
                   "Se emitió constancia de falta de información (DSO/DPO/CCC/aging).")

    # === Header de KPIs (cards) ===
    kpis_exec = (result.get("gerente", {})
                     .get("executive_decision_bsc", {})
                     .get("kpis") or {})
    kpis_top = (result.get("metrics") or {}) | kpis_exec
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("DSO (cobros)", _fmt_days(kpis_top.get("dso") or kpis_top.get("DSO")))
    with c2:
        st.metric("DPO (pagos)", _fmt_days(kpis_top.get("dpo") or kpis_top.get("DPO")))
    with c3:
        st.metric("CCC (ciclo de caja)", _fmt_days(kpis_top.get("ccc") or kpis_top.get("CCC")))
    st.divider()

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

    # === Antigüedad de saldos (vencido) ===
    st.subheader("📊 Antigüedad de saldos (solo vencido)")
    col_cxc, col_cxp = st.columns(2, gap="large")
    with col_cxc:
        st.caption("CxC (clientes)")
        a = _get_aging_from_result(result, "aaav_cxc")
        st.table(pd.DataFrame([a], index=["Monto"]).style.format("{:,.2f}"))
        if sum(a.values()) > 0:
            st.bar_chart(pd.Series(a), height=160, use_container_width=True)
    with col_cxp:
        st.caption("CxP (proveedores)")
        a = _get_aging_from_result(result, "aaav_cxp")
        st.table(pd.DataFrame([a], index=["Monto"]).style.format("{:,.2f}"))
        if sum(a.values()) > 0:
            st.bar_chart(pd.Series(a), height=160, use_container_width=True)

    # === Totales por módulo (si disponibles) ===
    st.subheader("💵 Totales (si disponibles)")
    t1, t2 = st.columns(2)
    with t1:
        st.caption("CxC")
        st.table(pd.DataFrame([_get_totals(result, "aaav_cxc")]).style.format("{:,.2f}"))
    with t2:
        st.caption("CxP")
        st.table(pd.DataFrame([_get_totals(result, "aaav_cxp")]).style.format("{:,.2f}"))

    # Hallazgos y órdenes
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("🧭 Hallazgos")
        findings = admin.get("hallazgos") or []
        if not findings:
            st.caption("Sin hallazgos.")
        else:
            # Acepta tanto lista de dicts (Admin) como lista de strings (fallback)
            for h in findings:
                if isinstance(h, dict):
                    with st.expander(h.get("msg", h.get("id", "Hallazgo")), expanded=False):
                        st.write({k: v for k, v in h.items() if k not in {"msg"}})
                else:
                    st.markdown(f"- {h}")
    with c2:
        st.subheader("🛠️ Órdenes")
        orders = admin.get("orders") or (gerente.get("executive_decision_bsc", {}).get("ordenes_prioritarias") or [])
        if not orders:
            st.caption("Sin órdenes.")
        else:
            for o in orders:
                title = (o.get("title") if isinstance(o, dict) else str(o)) or "Orden"
                with st.expander(title, expanded=False):
                    st.write(o)

    # Intent & trace
    with st.expander("🔎 Intent & Trace", expanded=show_trace):
        st.write({"intent": result.get("intent")})
        st.json(result.get("trace") or result, expanded=False)

    # -------------------------
    # Última casilla / conclusión
    # -------------------------
    with st.container(border=True):
        st.subheader("🧾 Conclusión del informe")
        if has_core:
            st.markdown(
                "- El informe **se generó correctamente** y contiene análisis sobre DSO, DPO y CCC.\n"
                "- Se incluyen hallazgos y órdenes priorizadas cuando aplica."
            )
        else:
            st.markdown(
                "- El informe **se generó** pero **no cuenta con datos suficientes** para un análisis completo.\n"
                "- **Acción sugerida:** cargar/validar DSO, DPO, CCC y el *aging* de CxC/CxP para habilitar los diagnósticos."
            )
