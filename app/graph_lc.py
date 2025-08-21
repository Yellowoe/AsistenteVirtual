from app.agents.intent import route_intent

def run_query(question: str, period: str | None = None) -> dict:
    # 1) Router de intención (nuevo)
    intent = route_intent(question)

    # 2) Ejecuta agentes según intención (tu lógica existente)
    from app.agents.registry import get_agent
    from app.state import GlobalState

    state = GlobalState(period=period or "2025-08")
    trace = []

    if intent.cxc:
        res_cxc = get_agent("aaav_cxc").handle({"payload": {"period": state.period}}, state)
        trace.append(res_cxc)
    else:
        res_cxc = None

    if intent.cxp:
        res_cxp = get_agent("aaav_cxp").handle({"payload": {"period": state.period}}, state)
        trace.append(res_cxp)
    else:
        res_cxp = None

    res_pack = None
    if intent.cxc and intent.cxp:
        res_pack = get_agent("aav_contable").handle({
            "payload": {
                "cxc_data": (res_cxc or {}).get("data"),
                "cxp_data": (res_cxp or {}).get("data"),
            }
        }, state)
        trace.append(res_pack)

    # Si pide informe, delega a gerente (opcional según tu implementación)
    res_gerente = None
    if intent.informe:
        res_gerente = get_agent("av_gerente").handle({
            "payload": {
                "question": question,
                "period": state.period
            }
        }, state)

    return {
        "intent": intent.model_dump(),
        "trace": trace,
        "gerente": res_gerente
    }
