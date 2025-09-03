from typing import Dict, Any, List
from .agents.registry import get_agent, AGENT_INFO
from .state import GlobalState
from .agents.av_gerente.classifier import classify_intent
from .lc_llm import get_chat_model

def refine_agent_sequence_with_llm(question: str, initial_agents: List[str]) -> List[str]:
    llm = get_chat_model()
    agent_list_str = ", ".join(initial_agents)
    all_agents_str = ", ".join(f"{k}: {v}" for k, v in AGENT_INFO.items())
    system = (
        "Eres un asistente experto en orquestar agentes virtuales para responder preguntas empresariales. "
        "Tu tarea es revisar la lista de agentes sugeridos por un clasificador y, si falta alguno relevante para la pregunta, "
        "agregarlo. Devuelve solo una lista de nombres de agentes separados por coma."
    )
    user = (
        f"Pregunta: {question}\n"
        f"Agentes sugeridos: {agent_list_str}\n"
        f"Agentes disponibles: {all_agents_str}\n"
        "¿Qué agentes deberían participar para responder correctamente? Devuelve solo los nombres separados por coma."
    )
    response = llm.invoke([
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ])
    # Procesa la respuesta para obtener la lista final
    agents = [a.strip() for a in response.content.split(",") if a.strip() in AGENT_INFO]
    # Si el LLM no devuelve nada válido, usa la lista inicial
    return agents if agents else initial_agents

class Router:
    def __init__(self, default_agent: str = "av_gerente"):
        self.default_agent = default_agent

    def dispatch(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        payload = task.get("payload", {})
        question = payload.get("question", "")
        period = payload.get("period", state.period)

        # 1. Clasificador tradicional
        agent_sequence: List[str] = classify_intent(question)
        # 2. Refinamiento con LLM
        agent_sequence = refine_agent_sequence_with_llm(question, agent_sequence)

        trace = []
        for agent_name in agent_sequence:
            agent = get_agent(agent_name)
            result = agent.handle({"payload": {"question": question, "period": period}}, state)
            result["agent"] = agent_name
            trace.append(result)

        gerente = get_agent("av_gerente")
        final_report = gerente.handle({
            "payload": {
                "trace": trace,
                "question": question,
                "period": period
            }
        }, state)

        return final_report
