from typing import Literal

AgentName = Literal["aaav_cxc","aaav_cxp","aav_contable","av_administrativo"]

def classify_intent(question: str) -> list[AgentName]:
    q = (question or "").lower()
    seq: list[AgentName] = []
    if any(k in q for k in ["cxc","cobrar","cliente","factura cliente","cuentas por cobrar"]):
        seq.append("aaav_cxc")
    if any(k in q for k in ["cxp","pagar","proveedor","cuentas por pagar","oc","orden de compra"]):
        seq.append("aaav_cxp")
    if any(k in q for k in ["estado financiero","er","esf","cierre","contable","balanza"]):
        seq.append("aav_contable")
    if any(k in q for k in ["resumen","informe","decisiones","ejecutivo","administrativo"]):
        seq.append("av_administrativo")

    if not seq:
        # default pipeline: CxC + CxP → Contable → Administrativo
        seq = ["aaav_cxc","aaav_cxp","aav_contable","av_administrativo"]
    # quita duplicados manteniendo orden
    seen=set(); seq=[x for x in seq if not (x in seen or seen.add(x))]
    return seq
