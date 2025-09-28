# app/utils/intent_es.py
import re
import unicodedata
from datetime import datetime
from dateutil.relativedelta import relativedelta

def _normalize_es(text: str) -> str:
    text = text.lower().strip()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text

TRIGGERS_INFORME = {
    r"\b(reporte|informe|resumen)\b",
    r"\b(estado[s]?\s+financier[oa]s?)\b",
    r"\b(crea(r|me|nos)?|genera(r|me|nos)?|haz|haga)\b.*\b(reporte|informe)\b",
}
TRIGGERS_FINANZAS = {
    r"\b(financiero|finanzas|kpi[s]?|indicadores|liquidez|efectivo|cashflow|flujo\s+de\s+caja|margen)\b",
}
TRIGGERS_CXC = {
    r"\b(cuentas?\s+por\s+cobrar|cxc|clientes|aging|antiguedad\s+de\s+saldos?)\b",
    r"\b(dso|days\s+sales\s+outstanding)\b",
    r"\b(morosidad|cartera|vencidas?)\b",
}
TRIGGERS_CXP = {
    r"\b(cuentas?\s+por\s+pagar|cxp|proveedores)\b",
    r"\b(dpo|days\s+payables?\s+outstanding)\b",
}

def detect_intent_es(question: str) -> dict:
    q = _normalize_es(question)
    def any_match(patterns): return any(re.search(p, q) for p in patterns)

    informe = any_match(TRIGGERS_INFORME) or any_match(TRIGGERS_FINANZAS)
    cxc = any_match(TRIGGERS_CXC) or ("reporte" in q and "financ" in q)
    cxp = any_match(TRIGGERS_CXP) or ("reporte" in q and "financ" in q)
    reason = f"heurística es-ES v2: informe={informe} cxc={cxc} cxp={cxp}"
    return {"informe": informe, "cxc": cxc, "cxp": cxp, "reason": reason}

def extract_period_es(question: str, now: datetime | None = None) -> str:
    q = _normalize_es(question)
    now = now or datetime.now()

    if re.search(r"\beste\s+mes\b", q):
        return now.strftime("%Y-%m")
    if re.search(r"\b(mes\s+pasado|mes\s+anterior)\b", q):
        d = now - relativedelta(months=1)
        return d.strftime("%Y-%m")

    MES = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
           "julio":7,"agosto":8,"setiembre":9,"septiembre":9,"octubre":10,
           "noviembre":11,"diciembre":12,"ene":1,"feb":2,"mar":3,"abr":4,
           "may":5,"jun":6,"jul":7,"ago":8,"sep":9,"set":9,"oct":10,"nov":11,"dic":12}
    m = re.search(r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|setiembre|septiembre|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)\s*(\d{4})?\b", q)
    if m:
        mes_txt, year_txt = m.group(1), m.group(2)
        y = int(year_txt) if year_txt else now.year
        mm = MES.get(mes_txt, now.month)
        return f"{y:04d}-{mm:02d}"

    return now.strftime("%Y-%m")
