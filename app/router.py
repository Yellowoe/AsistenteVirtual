from typing import Dict, Any, List
from .agents.registry import get_agent, AGENT_INFO
from .state import GlobalState
from .agents.av_gerente.classifier import classify_intent
from .lc_llm import get_chat_model

# 👇 nuevo
from .utils.intent_es import detect_intent_es, extract_period_es

FINANCIAL_DEFAULT_CHAIN = ["aaav_cxc", "aaav_cxp", "aav_contable"]  # Gerente siempre al final

def refine_agent_sequence_with_llm(question: str, initial_agents: List[str]) -> List[str]:
    llm = get_chat_model()
    agent_list_str = ", ".join(initial_agents)
    all_agents_str = ", ".join(f"{k}: {v}" for k, v in AGENT_INFO.items())
    system = (
        "Eres un asistente experto en orquestar agentes virtuales para responder preguntas empresariales. "
        "Revisa la lista de agentes sugeridos y agrega los que falten. Devuelve solo nombres separados por coma."
    )
    user = (
        f"Pregunta: {question}\n"
        f"Agentes sugeridos: {agent_list_str}\n"
        f"Agentes disponibles: {all_agents_str}\n"
        "¿Qué agentes deberían participar? Solo los nombres separados por coma."
    )
    response = llm.invoke([
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ])
    agents = [a.strip() for a in response.content.split(",") if a.strip() in AGENT_INFO]
    return agents if agents else initial_agents

def _dedup_preserving_order(names: List[str]) -> List[str]:
    seen, out = set(), []
    for n in names:
        if n not in seen:
            out.append(n); seen.add(n)
    return out

class Router:
    def __init__(self, default_agent: str = "av_gerente"):
        self.default_agent = default_agent

    def dispatch(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        payload = task.get("payload", {})
        question = payload.get("question", "")
        period = payload.get("period") or state.period or extract_period_es(question)

        # 0) Heurística ES + fail-safe
        es_intent = detect_intent_es(question)

        # 1) Clasificador tradicional
        agent_sequence: List[str] = classify_intent(question) or []

        # 2) Refinamiento con LLM (opcional)
        agent_sequence = refine_agent_sequence_with_llm(question, agent_sequence)

        # 3) Si es reporte/informe financiero, asegurar cadena mínima CxC→CxP→Contable
        if es_intent.get("informe"):
            for a in FINANCIAL_DEFAULT_CHAIN:
                if a not in agent_sequence:
                    agent_sequence.append(a)

        # 4) Nunca ejecutar gerente dentro del loop; va al final
        agent_sequence = [a for a in agent_sequence if a != "av_gerente"]
        agent_sequence = _dedup_preserving_order(agent_sequence)

        # 5) Trace básico
        if not hasattr(state, "trace"):
            state.trace = []
        state.trace.append({
            "intent_router_es": es_intent,
            "agent_sequence_before": classify_intent(question),
            "agent_sequence_final": agent_sequence,
            "question": question,
            "period": period
        })

        # 6) Ejecutar subagentes en orden
        trace: List[Dict[str, Any]] = []
        for agent_name in agent_sequence:
            agent = get_agent(agent_name)
            try:
                result = agent.handle({"payload": {"question": question, "period": period}}, state)
            except TypeError:
                # por si tu handle usa firma distinta
                result = agent.handle({"payload": {"period": period}}, state)
            result["agent"] = agent_name
            trace.append(result)

        # 7) Gerente al final, con el contexto ya enriquecido
        gerente = get_agent("av_gerente")
        final_report = gerente.handle({
            "payload": {
                "trace": trace,
                "question": question,
                "period": period
            }
        }, state)

        # 8) Meta útil para depurar
        final_report = final_report or {}
        final_report.setdefault("_meta", {})
        final_report["_meta"]["router_sequence"] = agent_sequence + ["av_gerente"]
        final_report["_meta"]["intent_router_es"] = es_intent
        final_report["_meta"]["period_resolved"] = period
        return final_report
