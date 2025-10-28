# app/agents/av_gerente/logic.py
from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
import re
import json
from datetime import datetime
import pandas as pd
from dateutil import parser as dateparser

from ..base import BaseAgent
from ...state import GlobalState
from ...lc_llm import get_chat_model
from ...tools.prompting import build_system_prompt
from ...tools.fuzzy import fuzzify_dso, fuzzify_dpo, fuzzify_ccc, liquidity_risk
from ...tools.causality import causal_hypotheses


class Agent(BaseAgent):
    """
    AV_Gerente — Enfoque BSC (Kaplan & Norton), causalidad y recomendaciones.
    - NUNCA inventa KPIs: usa solo lo que llegue en trace (CxC/CxP/Contable).
    - Genera órdenes con due date consistente con el período resuelto.
    """

    name = "av_gerente"
    role = "executive"

    MAX_TRACE_ITEMS: int = 30
    MAX_FIELD_CHARS: int = 2_000

    # -------------------------
    # Helpers generales
    # -------------------------
    def _to_jsonable(self, obj: Any) -> Any:
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if isinstance(obj, dict):
            return {str(k): self._to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [self._to_jsonable(v) for v in obj]
        # Objetos tipo fuzzy con atributos low/mid/high → dict
        if all(hasattr(obj, a) for a in ("low", "mid", "high")):
            try:
                return {
                    "low": float(getattr(obj, "low")),
                    "mid": float(getattr(obj, "mid")),
                    "high": float(getattr(obj, "high")),
                }
            except Exception:
                pass
        for attr in ("to_dict", "as_dict", "model_dump", "dict"):
            if hasattr(obj, attr):
                try:
                    v = getattr(obj, attr)()
                    return self._to_jsonable(v)
                except Exception:
                    pass
        try:
            return {str(k): self._to_jsonable(v) for k, v in obj.items()}  # type: ignore
        except Exception:
            pass
        try:
            return [self._to_jsonable(v) for v in obj]  # type: ignore
        except Exception:
            pass
        return str(obj)

    def _coerce_float(self, value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    def _truncate(self, s: str, max_len: int) -> str:
        if s is None:
            return ""
        if len(s) <= max_len:
            return s
        return s[: max_len - 1] + "…"

    def _sanitize_text(self, s: str) -> str:
        if not isinstance(s, str):
            return s
        s = re.sub(r"(?is)<\s*think\s*>.*?</\s*think\s*>", "", s)
        s = re.sub(r"(?is)```(?:json)?(.*?)```", r"\1", s)
        s = re.sub(r"(?is)^(thought|thinking|reasoning|chain\s*of\s*thought).*?(\n\n|$)", "", s)
        return s.strip()

    # -------------------------
    # Período helpers
    # -------------------------
    def _period_text_and_due(self, period_in: Any) -> tuple[str, str]:
        """
        Devuelve (period_text, due_yyyy_mm_30)
        - Si `period_in` es dict del router → usa 'text' si existe;
          si no, deriva YYYY-MM de 'start'.
        - Si es str (YYYY-MM) → úsalo directo.
        """
        period_text = ""
        if isinstance(period_in, dict):
            # preferimos texto “humano” si viene
            pt = str(period_in.get("text") or "").strip()
            if pt:
                period_text = pt
            else:
                # Derivar YYYY-MM de start si existe
                try:
                    start = dateparser.isoparse(period_in["start"])
                    period_text = f"{start.year:04d}-{start.month:02d}"
                except Exception:
                    period_text = ""
        elif isinstance(period_in, str):
            period_text = period_in.strip()

        # Construir due (YYYY-MM-30) tomando YYYY-MM de period_text si está,
        # si no, derivando de end/start si vienen
        due = "XXXX-XX-30"
        def _yyyy_mm_from_any(p: Any) -> Optional[str]:
            if isinstance(p, str) and len(p) >= 7 and p[4] == "-":
                return p[:7]
            if isinstance(p, dict):
                for key in ("start", "end"):
                    try:
                        dt = dateparser.isoparse(p[key])
                        return f"{dt.year:04d}-{dt.month:02d}"
                    except Exception:
                        pass
            return None

        ym = _yyyy_mm_from_any(period_text) or _yyyy_mm_from_any(period_in)
        if ym:
            due = f"{ym}-30"
        return period_text or (ym or ""), due

    # -------------------------
    # Extracción de datos del trace
    # -------------------------
    def _summarize_trace(self, trace: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
        if not trace:
            return "(sin resultados de subagentes)", {"dso": None, "dpo": None, "ccc": None, "cash": None}
        trimmed = trace[: self.MAX_TRACE_ITEMS]
        lines: List[str] = []
        dso = dpo = ccc = cash = None
        for res in trimmed:
            agent_name = res.get("agent", "Agente")
            summary = res.get("summary")
            if not isinstance(summary, str):
                summary_candidates = []
                for k in ("status", "highlights", "top_issues", "notes"):
                    if k in res:
                        summary_candidates.append(f"{k}: {res[k]}")
                summary = "; ".join(map(str, summary_candidates)) or str({k: res[k] for k in list(res)[:6]})
            lines.append(f"{agent_name}: {self._truncate(summary, self.MAX_FIELD_CHARS)}")
            if dso is None and "dso" in res:
                dso = self._coerce_float(res.get("dso"))
            if dpo is None and "dpo" in res:
                dpo = self._coerce_float(res.get("dpo"))
            if ccc is None and "ccc" in res:
                ccc = self._coerce_float(res.get("ccc"))
            if cash is None and "cash" in res:
                cash = self._coerce_float(res.get("cash"))
        return "\n".join(lines), {"dso": dso, "dpo": dpo, "ccc": ccc, "cash": cash}

    def _extract_aging(self, trace: List[Dict[str, Any]], agent_name: str) -> Dict[str, Any]:
        for res in trace or []:
            if res.get("agent") == agent_name:
                data = res.get("data") or {}
                aging = data.get("aging")
                if isinstance(aging, dict):
                    return aging
        return {}

    def _extract_context(self, trace: List[Dict[str, Any]]) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {
            "kpis": {"DSO": None, "DPO": None, "DIO": None, "CCC": None},
            "aging_cxc": {},
            "aging_cxp": {},
            "balances": {},
        }
        # Aging CxC / CxP
        ctx["aging_cxc"] = self._extract_aging(trace, "aaav_cxc")
        ctx["aging_cxp"] = self._extract_aging(trace, "aaav_cxp")
        # KPIs + balances (del contable si existe)
        for res in trace or []:
            data = res.get("data") or {}
            kpi = data.get("kpi") or {}
            if isinstance(kpi, dict):
                for k in ("DSO", "DPO", "DIO", "CCC"):
                    if ctx["kpis"].get(k) is None and k in kpi:
                        ctx["kpis"][k] = self._coerce_float(kpi.get(k))
            bal = data.get("balances") or {}
            if isinstance(bal, dict) and not ctx["balances"]:
                ctx["balances"] = {str(k): self._coerce_float(v) for k, v in bal.items()}
        return ctx

    def _build_fuzzy_signals(self, metrics: Dict[str, Optional[float]]) -> Dict[str, Any]:
        dso, dpo, ccc, cash = metrics.get("dso"), metrics.get("dpo"), metrics.get("ccc"), metrics.get("cash")
        out: Dict[str, Any] = {}
        if dso is not None: out["dso"] = self._to_jsonable(fuzzify_dso(dso))
        if dpo is not None: out["dpo"] = self._to_jsonable(fuzzify_dpo(dpo))
        if ccc is not None: out["ccc"] = self._to_jsonable(fuzzify_ccc(ccc))
        if cash is not None and ccc is not None: out["liquidity_risk"] = self._to_jsonable(liquidity_risk(cash, ccc))
        return out

    # -------------------------
    # Causalidad y órdenes deterministas
    # -------------------------
    def _derive_deterministic_causality(self, ctx: Dict[str, Any]) -> List[str]:
        k = ctx.get("kpis", {})
        aging_cxp = ctx.get("aging_cxp") or {}
        hyps = []
        dso = k.get("DSO"); dpo = k.get("DPO"); ccc = k.get("CCC")
        if isinstance(dso, (int, float)) and dso > 45:
            hyps.append("DSO alto sugiere fricción en cobranza o crédito laxo (segmentos/condiciones).")
        if isinstance(dpo, (int, float)) and dpo < 40:
            hyps.append("DPO bajo indica negociación débil o pagos anticipados no alineados a caja.")
        if isinstance(ccc, (int, float)) and ccc > 20:
            hyps.append("CCC positivo alto indica presión de caja; probable inventario/AR alto vs AP.")
        share_31_60 = aging_cxp.get("31_60")
        if isinstance(share_31_60, (int, float)) and share_31_60 > 0:
            hyps.append("Proporción relevante de CxP en 31–60 días puede tensar pagos si no se calendariza.")
        return hyps

    def _deterministic_orders(self, ctx: Dict[str, Any], period_in: Any) -> List[Dict[str, Any]]:
        k = ctx.get("kpis", {})
        bal = ctx.get("balances", {})
        dso = k.get("DSO"); dpo = k.get("DPO"); ccc = k.get("CCC")
        ar = bal.get("AR_outstanding"); ap = bal.get("AP_outstanding")
        ratio = (ar / ap) if isinstance(ar, (int, float)) and isinstance(ap, (int, float)) and ap > 0 else None

        # due consistente con período dict/string
        _, due = self._period_text_and_due(period_in)

        orders: List[Dict[str, Any]] = []
        if isinstance(dso, (int, float)) and dso > 45:
            orders.append({"title":"Campaña dunning top-10 clientes","owner":"CxC","priority":"P1","kpi":"DSO","due":due})
        if isinstance(dpo, (int, float)) and dpo < 40:
            orders.append({"title":"Renegociar 3 proveedores clave","owner":"CxP","priority":"P2","kpi":"DPO","due":due})
        if isinstance(ccc, (int, float)) and ccc > 20:
            orders.append({"title":"Freeze gastos no esenciales (30d)","owner":"Administración","priority":"P1","kpi":"CCC","due":due})
        if isinstance(ratio, float) and ratio > 1.30:
            orders.append({"title":"Sync semanal CxC/CxP sobre flujos","owner":"Administración","priority":"P3","kpi":"CCC","due":due})
        return orders

    # -------------------------
    # LLM JSON parser robusto
    # -------------------------
    def _llm_json(self, llm, system_prompt: str, user_prompt: str) -> Optional[Any]:
        def _clean(s: str) -> str:
            return self._sanitize_text(s or "")
        def _try_parse_any_json(s: str) -> Optional[Any]:
            s = s.strip()
            if s.startswith("{") or s.startswith("["):
                try:
                    return json.loads(s)
                except Exception:
                    pass
            starts = [m.start() for m in re.finditer(r"[\{\[]", s)]
            ends   = [m.start() for m in re.finditer(r"[\}\]]", s)]
            for i in range(len(starts)):
                for j in range(len(ends)-1, i-1, -1):
                    if ends[j] <= starts[i]:
                        continue
                    frag = s[starts[i]:ends[j]+1]
                    try:
                        return json.loads(frag)
                    except Exception:
                        continue
            return None

        try:
            resp = llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]).content
        except Exception:
            return None
        return _try_parse_any_json(_clean(resp))

    # -------------------------
    # Fallback y post-proceso
    # -------------------------
    def _fallback_report(self, ctx: Dict[str, Any], fuzzy_signals: Dict[str, Any],
                         causal_traditional: List[str], causal_llm: List[str]) -> Dict[str, Any]:
        k = ctx.get("kpis", {})
        dso = k.get("DSO"); dpo = k.get("DPO"); ccc = k.get("CCC")

        hallazgos, riesgos, reco = [], [], []

        if isinstance(dso, (int, float)) and dso > 45:
            hallazgos.append(f"DSO por encima del umbral (>{45}d): {dso:.1f}d")
            reco.append("Campaña dunning top-10 clientes (30-60-90).")
        if isinstance(dpo, (int, float)) and dpo < 40:
            hallazgos.append(f"DPO por debajo del umbral (<{40}d): {dpo:.1f}d")
            reco.append("Renegociar 2–3 proveedores para ampliar plazos.")
        if isinstance(ccc, (int, float)) and ccc > 20:
            hallazgos.append(f"CCC elevado (>20d): {ccc:.1f}d")
            reco.append("Calendario AR/AP semanal y control de gastos no esenciales (30d).")
        if not hallazgos:
            hallazgos.append("KPIs dentro de rangos razonables para el mes.")
            reco.append("Mantener disciplina de caja y seguimiento semanal de aging.")

        if isinstance(ccc, (int, float)) and ccc > 0:
            riesgos.append("Presión de caja por ciclo de conversión positivo.")
        if isinstance(dso, (int, float)) and isinstance(dpo, (int, float)) and (dso - dpo) > 10:
            riesgos.append("Desbalance entre cobros y pagos (DSO >> DPO).")
        if not riesgos:
            riesgos.append("Riesgo moderado; continuar monitoreo semanal de AR/AP.")

        resumen = (
            f"KPIs: DSO={dso if dso is not None else 'N/D'}d, "
            f"DPO={dpo if dpo is not None else 'N/D'}d, "
            f"CCC={ccc if ccc is not None else 'N/D'}d. "
            "Informe estructurado con acciones tácticas para liquidez."
        )

        return {
            "resumen_ejecutivo": resumen,
            "hallazgos": hallazgos,
            "riesgos": riesgos,
            "recomendaciones": reco,
            "bsc": {
                "finanzas": [
                    f"DSO: {dso:.1f}d" if isinstance(dso, (int, float)) else "DSO: N/D",
                    f"DPO: {dpo:.1f}d" if isinstance(dpo, (int, float)) else "DPO: N/D",
                    f"CCC: {ccc:.1f}d" if isinstance(ccc, (int, float)) else "CCC: N/D",
                ],
                "clientes": ["Sin datos de NPS/Churn en este corte."],
                "procesos_internos": ["Revisión de aging AR/AP semanal."],
                "aprendizaje_crecimiento": ["Playbooks de cobranza y negociación de proveedores."],
            },
            "causalidad": {
                "hipotesis": list(dict.fromkeys((causal_traditional or []) + (causal_llm or [])))[:10],
                "enlaces": []
            },
            "ordenes_prioritarias": [],
            "_insumos": {"fuzzy_signals": fuzzy_signals},
        }

    def _post_process_report(self, report: Dict[str, Any], ctx: Dict[str, Any],
                             deterministic_orders: List[Dict[str, Any]],
                             causal_traditional: List[str], causal_llm: List[str]) -> Dict[str, Any]:
        if not isinstance(report, dict):
            return report

        # Asegura BSC.finanzas con KPIs reales
        bsc = report.get("bsc") if isinstance(report.get("bsc"), dict) else {}
        k = ctx.get("kpis", {})
        dso = k.get("DSO"); dpo = k.get("DPO"); ccc = k.get("CCC")
        bsc["finanzas"] = [
            f"DSO: {dso:.1f}d" if isinstance(dso, (int, float)) else "DSO: N/D",
            f"DPO: {dpo:.1f}d" if isinstance(dpo, (int, float)) else "DPO: N/D",
            f"CCC: {ccc:.1f}d" if isinstance(ccc, (int, float)) else "CCC: N/D",
        ]
        report["bsc"] = bsc

        # Inserta/une causalidad
        cz = report.get("causalidad")
        if not isinstance(cz, dict):
            cz = {}
        cz_h = cz.get("hipotesis", [])
        merged_h = list(dict.fromkeys((cz_h if isinstance(cz_h, list) else []) + (causal_traditional or []) + (causal_llm or [])))
        cz["hipotesis"] = merged_h[:10]
        if not isinstance(cz.get("enlaces"), list):
            cz["enlaces"] = []
        report["causalidad"] = cz

        # Inserta/une órdenes
        curr_orders = report.get("ordenes_prioritarias")
        if not isinstance(curr_orders, list):
            curr_orders = []
        # dedup por título
        seen = set()
        merged_orders: List[Dict[str, Any]] = []
        for o in list(curr_orders) + deterministic_orders:
            title = (o or {}).get("title")
            if not title or title in seen: continue
            seen.add(title); merged_orders.append(o)
        report["ordenes_prioritarias"] = merged_orders

        # Sanitiza textos
        if isinstance(report.get("resumen_ejecutivo"), str):
            report["resumen_ejecutivo"] = self._sanitize_text(report["resumen_ejecutivo"])
        for sec in ("hallazgos","riesgos","recomendaciones"):
            if isinstance(report.get(sec), list):
                report[sec] = [self._sanitize_text(str(x)) for x in report[sec]]

        return report

    # -------------------------
    # Handler principal
    # -------------------------
    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        payload = task.get("payload", {})
        question: str = payload.get("question", "")
        period_in: Any = payload.get("period", state.period)
        trace: List[Dict[str, Any]] = payload.get("trace", []) or []

        # 1) Resumen y métricas top-level
        resumen, metrics = self._summarize_trace(trace)

        # 2) Contexto data-grounded + fuzzy (solo como señal cualitativa)
        ctx = self._extract_context(trace)
        fuzzy_signals = self._build_fuzzy_signals(metrics)

        # 3) Causalidad tradicional (reglas + aging)
        try:
            causal_traditional = causal_hypotheses(trace, ctx.get("aging_cxc") or {}, ctx.get("aging_cxp") or {})
        except TypeError:
            causal_traditional = causal_hypotheses(trace)

        # 4) Órdenes deterministas (no dependen del LLM)
        det_orders = self._deterministic_orders(ctx, period_in)

        # 5) LLM — instrucciones estrictas BSC + causalidad (SIN inventar números)
        llm = get_chat_model()
        system_prompt = build_system_prompt(self.name)

        guardrails = (
            "REGLAS ESTRICTAS:\n"
            "1) DATOS:\n"
            "   • Usa SOLO los datos explícitos de 'context.kpis', 'context.balances' y 'context.aging_cxc/cxp'.\n"
            "   • Si un dato no está presente, escribe 'N/D'.\n"
            "2) Fuzzy:\n"
            "   • 'fuzzy_signals' son cualitativos (low/mid/high). NO los uses como KPI ni los conviertas a valores numéricos.\n"
            "3) Comparaciones intermensuales:\n"
            "   • PROHIBIDO afirmar 'mejor/peor', 'al alza/a la baja', o comparar con 'el mes anterior' si NO existe 'context.prev_kpis'.\n"
            "4) DPO y CCC (semántica correcta):\n"
            "   • En este sistema: CCC = DSO − DPO. Un DPO alto, en aislamiento, TIENDE a mejorar (hacer más negativo) el CCC.\n"
            "   • El riesgo con CxP proviene de tener AP VENCIDO (aging_cxp > 0), NO del nivel de DPO por sí mismo.\n"
            "5) Aging:\n"
            "   • 'vencido' = facturas con days_overdue > 0. NO llames 'por vencer' a lo que ya está vencido.\n"
            "   • Usa explícitamente las sumas por buckets: 0_30, 31_60, 61_90, 90_plus.\n"
            "6) Inventarios/DIO:\n"
            "   • NO menciones inventario ni DIO ni los uses para causalidad si NO existe 'context.kpis.DIO' o datos de inventarios.\n"
            "7) Salida:\n"
            "   • Devuelve ÚNICAMENTE JSON VÁLIDO con la estructura indicada. Sin explicaciones, sin bloques <think>.\n"
        )

        period_text, _ = self._period_text_and_due(period_in)

        user_prompt = (
            f"{guardrails}\n"
            f"Periodo: {period_text}\n"
            f"Pregunta: {question}\n\n"
            f"== CONTEXTO ==\n"
            f"KPIs: {ctx.get('kpis')}\n"
            f"Aging CxC: {ctx.get('aging_cxc')}\n"
            f"Aging CxP: {ctx.get('aging_cxp')}\n"
            f"Balances: {ctx.get('balances')}\n\n"
            f"Resumen de subagentes:\n{resumen}\n\n"
            "Devuelve EXACTAMENTE este JSON:\n"
            "{\n"
            "  'resumen_ejecutivo': str,\n"
            "  'hallazgos': [str],\n"
            "  'riesgos': [str],\n"
            "  'recomendaciones': [str],\n"
            "  'bsc': {\n"
            "    'finanzas': [str],\n"
            "    'clientes': [str],\n"
            "    'procesos_internos': [str],\n"
            "    'aprendizaje_crecimiento': [str]\n"
            "  },\n"
            "  'causalidad': {\n"
            "    'hipotesis': [str],\n"
            "    'enlaces': [ {'causa': str, 'efecto': str, 'evidencia': str, 'confianza': 'alta|media|baja'} ]\n"
            "  },\n"
            "  'ordenes_prioritarias': [ {'title': str, 'owner': str, 'kpi': str, 'due': str, 'impacto': str} ]\n"
            "}\n"
        )

        report_json = self._llm_json(llm, system_prompt, user_prompt)

        # 6) Fallback si el LLM no devuelve JSON válido
        if not isinstance(report_json, dict):
            fallback = self._fallback_report(ctx, fuzzy_signals, causal_traditional, [])
            fallback["ordenes_prioritarias"] = det_orders  # inserta órdenes deterministas
            return {
                "executive_decision_bsc": fallback,
                "question": question,
                "period": period_in,
                "trace": trace,
                "metrics": metrics,
                "fuzzy_signals": fuzzy_signals,
                "causal_hypotheses": causal_traditional,
                "causal_hypotheses_llm": [],
                "_meta": {"structured": True, "llm_ok": False},
            }

        # 7) Post-proceso: fuerza BSC.finanzas con KPIs reales + une causalidad + añade órdenes deterministas
        final_report = self._post_process_report(
            report_json, ctx, det_orders, causal_traditional, report_json.get("causalidad", {}).get("hipotesis", [])
        )

        return {
            "executive_decision_bsc": final_report,
            "question": question,
            "period": period_in,
            "trace": trace,
            "metrics": metrics,
            "fuzzy_signals": fuzzy_signals,
            "causal_hypotheses": causal_traditional,
            "causal_hypotheses_llm": final_report.get("causalidad", {}).get("hipotesis", []),
            "_meta": {"structured": True, "llm_ok": True},
        }
