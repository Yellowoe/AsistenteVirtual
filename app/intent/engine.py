# app/intent/engine.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import json
import re

from app.utils.intent_es import (
    _normalize_es,
    TRIGGERS_INFORME,
    TRIGGERS_FINANZAS,
    TRIGGERS_CXC,
    TRIGGERS_CXP,
)
from app.lc_llm import get_chat_model

# Umbrales (puedes afinar luego)
KW_MIN_SCORE = 1.25   # sube/baja según falsos positivos
LLM_MIN_CONF = 0.60   # confianza mínima del LLM

# ---- Compilación de patrones (evita “parsear” regex a frases) ----
def _compile_set(patterns: set[str]) -> List[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]

RX_INFORME   = _compile_set(TRIGGERS_INFORME)
RX_FIN       = _compile_set(TRIGGERS_FINANZAS)
RX_CXC       = _compile_set(TRIGGERS_CXC)
RX_CXP       = _compile_set(TRIGGERS_CXP)

# Señales de KPI / módulo por contains simple (además de regex)
KPI_TOKENS   = {"dso": 0.8, "dpo": 0.8, "ccc": 0.8, "ebitda": 0.6, "margen": 0.6, "aging": 0.9}
MOD_TOKENS   = {"cxc": 1.2, "cuentas por cobrar": 1.2, "cxp": 1.2, "cuentas por pagar": 1.2}

def _score_regex(text: str, patterns: List[re.Pattern]) -> float:
    return 1.0 if any(p.search(text) for p in patterns) else 0.0

def keyword_scores(question: str) -> Dict[str, float]:
    """
    Puntuación determinística por agente usando:
    - Coincidencias REGEX de tus TRIGGERS_* (1.0 por familia)
    - Tokens KPI/Módulo (ponderados)
    - Señales transversales (informe/finanzas) suman a contable y a ambos auxiliares
    """
    t = _normalize_es(question or "")

    # regex “familias”
    fin_hit   = _score_regex(t, RX_FIN)      # finanzas/liquidez/etc.
    rep_hit   = _score_regex(t, RX_INFORME)  # informe/reporte/analisis financiero
    cxc_hit   = _score_regex(t, RX_CXC)
    cxp_hit   = _score_regex(t, RX_CXP)

    # tokens simples
    kpi_bonus = {k: 0.0 for k in ("cxc","cxp","cont")}
    for tok, w in KPI_TOKENS.items():
        if tok in t:
            if tok == "dso":
                kpi_bonus["cxc"] += w
            elif tok == "dpo":
                kpi_bonus["cxp"] += w
            elif tok in ("ccc","ebitda","margen"):
                kpi_bonus["cont"] += w
            elif tok == "aging":
                # aging suele aplicar a ambos auxiliares
                kpi_bonus["cxc"] += w * 0.7
                kpi_bonus["cxp"] += w * 0.7

    for tok, w in MOD_TOKENS.items():
        if tok in t:
            if "cobrar" in tok or "cxc" in tok:
                kpi_bonus["cxc"] += w
            if "pagar" in tok or "cxp" in tok:
                kpi_bonus["cxp"] += w

    # Sumas por agente
    scores = {
        "aaav_cxc":  cxc_hit + fin_hit*0.4 + rep_hit*0.4 + kpi_bonus["cxc"],
        "aaav_cxp":  cxp_hit + fin_hit*0.4 + rep_hit*0.4 + kpi_bonus["cxp"],
        "aav_contable": fin_hit*0.8 + rep_hit*1.0 + kpi_bonus["cont"],
        "av_administrativo": rep_hit*0.6,  # se activará más cuando pidas BSC/órdenes
    }
    return scores

def llm_proposal(question: str) -> List[Tuple[str, float, str]]:
    """
    Pide al LLM sugerir agentes y confianza. Devuelve [(agent, confidence, reason)].
    """
    llm = get_chat_model()
    roles = [
        {"name": "aaav_cxc", "role": "CxC"},
        {"name": "aaav_cxp", "role": "CxP"},
        {"name": "aav_contable", "role": "Contable"},
        {"name": "av_administrativo", "role": "Administrativo"},
        {"name": "av_gerente", "role": "Gerente"},
    ]
    system = (
        "Eres un orquestador de agentes. Según la pregunta del usuario, "
        "elige qué agentes deben participar. Devuelve JSON con formato: "
        "{\"agents\":[{\"name\":\"...\",\"confidence\":0..1,\"reason\":\"...\"}]}.\n"
        "Evalúa CxC, CxP, Contable y Administrativo. Si no hay suficiente señal, usa confidence<0.5."
    )
    user = f"Pregunta: {question}\nAgentes:\n{json.dumps(roles, ensure_ascii=False)}\nResponde SOLO JSON."
    resp = llm.invoke([{"role":"system","content":system},{"role":"user","content":user}])
    try:
        txt = resp.content
        txt = txt[txt.find("{"): txt.rfind("}")+1]
        data = json.loads(txt)
        out = []
        for a in data.get("agents", []):
            name = (a.get("name") or "").strip()
            conf = float(a.get("confidence", 0))
            reason = a.get("reason") or ""
            out.append((name, conf, reason))
        return out
    except Exception:
        # Si falla el LLM, seguimos con keywords únicamente
        return []

def decide_agents(question: str) -> Dict[str, Any]:
    kw_scores = keyword_scores(question)
    kw_hits = [a for a, s in kw_scores.items() if s >= KW_MIN_SCORE]

    llm_list = llm_proposal(question)
    llm_hits = [(n,c,r) for (n,c,r) in llm_list if n in kw_scores and c >= LLM_MIN_CONF]

    selected = []
    seen = set()

    # Incluye los que pasan por keywords
    for a in kw_hits:
        if a not in seen:
            selected.append(a); seen.add(a)
    # y los del LLM
    for (n,_,_) in llm_hits:
        if n not in seen:
            selected.append(n); seen.add(n)

    reasons = {
        "thresholds": {"KW_MIN_SCORE": KW_MIN_SCORE, "LLM_MIN_CONF": LLM_MIN_CONF},
        "kw_scores": kw_scores,
        "kw_hits": kw_hits,
        "llm_list": [{"agent":n,"confidence":c,"reason":r} for (n,c,r) in llm_list],
        "llm_hits": [{"agent":n,"confidence":c,"reason":r} for (n,c,r) in llm_hits],
    }
    return {"selected": selected, "reasons": reasons}
