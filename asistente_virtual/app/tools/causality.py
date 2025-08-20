# app/tools/causality.py
from typing import List, Dict

def causal_hypotheses(kpi: Dict, aging_cxc: Dict, aging_cxp: Dict) -> List[Dict]:
    """
    Heurísticas causales simples (señales):
    - DSO alto: políticas de crédito laxas, disputas, baja eficiencia de cobranza, estacionalidad, concentración clientes.
    - DPO bajo: pérdida de poder de negociación, descuentos por pronto pago no aprovechados, políticas de pago rígidas.
    - CCC alto: inventario lento (si existiera), descalce cobro/pago.
    - CCC negativo: disciplina de cobro o plazos de pago largos.
    """
    ideas = []
    dso = (kpi or {}).get("DSO")
    dpo = (kpi or {}).get("DPO")
    ccc = (kpi or {}).get("CCC")

    cxc90 = float((aging_cxc or {}).get("90_plus", 0.0))
    cxc61_90 = float((aging_cxc or {}).get("61_90", 0.0))
    cxp31_60 = float((aging_cxp or {}).get("31_60", 0.0))

    if dso is not None:
        if dso >= 60 or cxc90 > 0:
            ideas.append({"cause":"Políticas de crédito laxas o límites altos",
                          "evidence":"DSO≥60 o bucket 90+ significativo",
                          "confidence":"high" if cxc90>0 else "medium"})
            ideas.append({"cause":"Disputas/errores de facturación",
                          "evidence":"Aging prolongado; revisar en 61-90/90+",
                          "confidence":"medium" if cxc61_90>0 else "low"})
            ideas.append({"cause":"Eficiencia de cobranza (dunning tardío)",
                          "evidence":"Poco movimiento en 0-30 vs 31-60/90+",
                          "confidence":"medium"})
        elif dso <= 35 and ccc is not None and ccc < 0:
            ideas.append({"cause":"Disciplina de cobro eficaz",
                          "evidence":"DSO bajo y CCC negativo",
                          "confidence":"high"})

    if dpo is not None:
        if dpo < 35:
            ideas.append({"cause":"Pagos prematuros o término de pago corto",
                          "evidence":"DPO bajo",
                          "confidence":"medium"})
        elif dpo >= 70:
            ideas.append({"cause":"Poder de negociación/financiamiento de proveedores",
                          "evidence":"DPO alto",
                          "confidence":"medium"})

    if ccc is not None:
        if ccc > 0:
            ideas.append({"cause":"Descalce cobros/pagos; presión de caja",
                          "evidence":"CCC positivo",
                          "confidence":"medium"})
        else:
            ideas.append({"cause":"Cobras antes de pagar (caja robusta)",
                          "evidence":"CCC negativo",
                          "confidence":"medium"})

    # dedup simple
    dedup = []
    seen = set()
    for i in ideas:
        key = (i["cause"], i["evidence"])
        if key not in seen:
            dedup.append(i); seen.add(key)
    return dedup[:6]
