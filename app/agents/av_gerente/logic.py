# app/agents/av_gerente/logic.py
from ..base import BaseAgent
from ...state import GlobalState
from typing import Dict, Any
from ...llm import LLM  # strip_think no es necesario si ya limpias en LLM.chat
from ...tools.prompting import build_system_prompt
from ...tools.fuzzy import fuzzify_dso, fuzzify_dpo, fuzzify_ccc, liquidity_risk
from ...tools.causality import causal_hypotheses


class Agent(BaseAgent):
    name = "av_gerente"
    role = "executive"

    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        from ..registry import get_agent  # lazy import

        q = task.get("payload", {}).get("question", "")
        period = task.get("payload", {}).get("period", state.period)

        trace = []

        # 1) Ejecuta pipeline base
        res_cxc = get_agent("aaav_cxc").handle({"payload": {"period": period}}, state)
        trace.append(res_cxc)
        res_cxp = get_agent("aaav_cxp").handle({"payload": {"period": period}}, state)
        trace.append(res_cxp)

        pack = None
        if not ("error" in res_cxc or "error" in res_cxp):
            res_pack = get_agent("aav_contable").handle(
                {"payload": {"cxc_data": res_cxc.get("data"),
                             "cxp_data": res_cxp.get("data")}},
                state,
            )
            trace.append(res_pack)
            pack = res_pack.get("data")

        # 2) Analítica difusa + causalidad
        fuzzy: Dict[str, Any] = {}
        causes = []
        if pack:
            k = pack.get("kpi", {})
            dso_f = fuzzify_dso(float(k.get("DSO") or 0))
            dpo_f = fuzzify_dpo(float(k.get("DPO") or 0))
            ccc_f = fuzzify_ccc(float(k.get("CCC") or 0))
            fuzzy = {
                "DSO": {"low": dso_f.low, "mid": dso_f.mid, "high": dso_f.high},
                "DPO": {"low": dpo_f.low, "mid": dpo_f.mid, "high": dpo_f.high},
                "CCC": {"low": ccc_f.low, "mid": ccc_f.mid, "high": ccc_f.high},
                "liquidity_risk": liquidity_risk(dso_f, dpo_f, ccc_f),
            }
            causes = causal_hypotheses(
                kpi=k,
                aging_cxc=((res_cxc.get("data") or {}).get("aging") or {}),
                aging_cxp=((res_cxp.get("data") or {}).get("aging") or {}),
            )

        # 3) Informe BSC + causalidad con LLM (deepseek-r1)
        decision_bsc = ""
        if pack:
            llm = LLM()
            system = build_system_prompt("av_gerente")

            k = (pack or {}).get("kpi", {})
            short_causes = causes[:3]
            liq = (fuzzy or {}).get("liquidity_risk", {})

            user = f"""
Idioma: Español (Costa Rica). Formato claro, con títulos y listas.

Contexto:
- Periodo: {period}
- KPIs: {k}
- Riesgo de liquidez (difuso): {liq}
- Hipótesis causales (top-3): {short_causes}
- Pregunta del usuario: {q or 'Genera un informe ejecutivo del periodo.'}

Tarea (obligatorio, no inventes datos):
1) Resumen Ejecutivo (5–8 líneas).
2) Balanced Scorecard — 4 perspectivas:
   - Financiera
   - Cliente
   - Procesos Internos
   - Aprendizaje y Crecimiento
   Para cada perspectiva: 2–3 objetivos con: KPI, meta (valor/fecha), iniciativa, RACI (R/A/C/I), fecha objetivo.
3) Causalidad: explica qué podría estar generando los KPIs (confianza: bajo/medio/alto). Usa señales difusas para priorizar.
4) ÓRDENES PRIORITARIAS (3–5): acciones concretas (responsable, impacto, fecha).
5) Riesgos y Supuestos (bullets).
""".strip()

            decision_bsc = llm.chat(system, user) or ""

        # ✅ Fallback determinista si sigue vacío
        if not decision_bsc.strip():
            k = (pack or {}).get("kpi", {})
            liq = (fuzzy or {}).get("liquidity_risk", {})
            decision_bsc = (
                "## Resumen Ejecutivo (fallback)\n"
                f"- Periodo: {period}\n"
                f"- KPIs: {k}\n"
                f"- Riesgo de liquidez (difuso): {liq}\n\n"
                "## Balanced Scorecard (mínimo)\n"
                "### Financiera\n"
                "- Objetivo: Mantener liquidez positiva.\n"
                "- KPI: CCC (meta ≤ 0 días). Iniciativa: reforzar cobranza en 0–30.\n"
                "### Cliente\n"
                "- Objetivo: Sostener pagos puntuales.\n"
                "- KPI: DSO (meta 30–35 días). Iniciativa: recordatorios preventivos.\n"
                "### Procesos Internos\n"
                "- Objetivo: Priorizar cartera con riesgo.\n"
                "- KPI: % en 61–90/90+. Iniciativa: dunning escalonado.\n"
                "### Aprendizaje y Crecimiento\n"
                "- Objetivo: Capacitación en políticas de crédito y negociación.\n\n"
                "## ÓRDENES PRIORITARIAS\n"
                "- CxC: contactar top-10 saldos abiertos en 48h (R: Cobranzas, Due: +7 días).\n"
                "- CxP: revisar oportunidades de pronto pago y cash-back (R: Tesorería, Due: +10 días).\n"
            )

        return {
            "agent": self.name,
            "summary": "Plan ejecutado + BSC + causalidad difusa",
            "plan": ["aaav_cxc", "aaav_cxp", "aav_contable", "av_administrativo"],
            "trace": trace,
            "fuzzy_signals": fuzzy,
            "causal_hypotheses": causes,
            "executive_decision_bsc": decision_bsc,
        }
