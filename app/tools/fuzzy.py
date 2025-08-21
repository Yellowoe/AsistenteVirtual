# app/tools/fuzzy.py
from dataclasses import dataclass

def _tri(x, a, b, c):
    # Triangular membership
    if x <= a or x >= c: return 0.0
    if x == b: return 1.0
    if x < b: return max((x - a) / (b - a + 1e-9), 0.0)
    return max((c - x) / (c - b + 1e-9), 0.0)

@dataclass
class FuzzySet:
    low: float
    mid: float
    high: float

def fuzzify_dso(x: float) -> FuzzySet:
    # Ajusta umbrales a tu negocio
    return FuzzySet(
        low=_tri(x, 0, 25, 40),
        mid=_tri(x, 30, 45, 60),
        high=_tri(x, 50, 70, 100),
    )

def fuzzify_dpo(x: float) -> FuzzySet:
    return FuzzySet(
        low=_tri(x, 0, 25, 40),
        mid=_tri(x, 30, 45, 60),
        high=_tri(x, 50, 70, 100),
    )

def fuzzify_ccc(x: float) -> FuzzySet:
    # CCC negativo suele ser bueno para caja
    return FuzzySet(
        low=_tri(x, -60, -30, 0),      # caja holgada
        mid=_tri(x, -10, 10, 30),      # neutral
        high=_tri(x, 20, 45, 90),      # presión de caja
    )

def liquidity_risk(dso: FuzzySet, dpo: FuzzySet, ccc: FuzzySet) -> dict:
    """
    Reglas simples:
    - Riesgo ALTO si (DSO alto) y (CCC alto).
    - Riesgo MEDIO si (DSO medio) o (CCC medio) y DPO bajo.
    - Riesgo BAJO si (CCC bajo) o (DPO alto y DSO bajo/medio).
    """
    high = min(dso.high, ccc.high)
    med = max(min(dso.mid, 1 - dpo.high), ccc.mid)
    low = max(ccc.low, min(dpo.high, max(dso.low, dso.mid)))

    # normaliza
    s = high + med + low + 1e-9
    return {"low": float(low/s), "medium": float(med/s), "high": float(high/s)}
