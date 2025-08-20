# app/tools/prompting.py
from pathlib import Path
import yaml

def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

def build_system_prompt(agent_name: str, extra: str = "") -> str:
    """
    Construye el prompt de sistema del agente.
    - Lee app/configs/personas.yaml si existe (opcional).
    - Acepta 'extra' para añadir instrucciones adicionales (como en av_gerente).
    """
    personas_path = Path("app/configs/personas.yaml")
    personas = _load_yaml(personas_path)

    base = personas.get("default", {})
    agent = personas.get(agent_name, {})

    tone = base.get("tone", "claro, directo, profesional")
    guardrails = "\n".join(f"- {g}" for g in base.get("guardrails", []))
    style = "\n".join(f"- {s}" for s in base.get("output_style", []))

    role = agent.get("role", agent_name)
    rules = "\n".join(f"- {r}" for r in agent.get("rules", []))

    # Si el agente es el gerente y definiste BSC/mentality en personas.yaml
    bsc_block = ""
    if agent_name == "av_gerente":
        mindset = agent.get("mindset", "")
        pr = agent.get("priorities", {})
        kpis = agent.get("kpi_library", {})
        bsc_block = f"""
[Mentalidad] {mindset}
[Prioridades]
- Financiera: {pr.get('financial','')}
- Cliente: {pr.get('customer','')}
- Procesos Internos: {pr.get('internal','')}
- Aprendizaje y Crecimiento: {pr.get('learning','')}
[KPIs sugeridos]
- Financiera: {', '.join(kpis.get('financial', []))}
- Cliente: {', '.join(kpis.get('customer', []))}
- Procesos: {', '.join(kpis.get('internal', []))}
- Aprendizaje: {', '.join(kpis.get('learning', []))}
""".strip()

    # 🚨 Reglas globales para TODOS los agentes:
    always_rules = """
- Da solo la conclusión o resultado final.
- No muestres razonamiento interno.
- No des explicaciones del proceso.
- Nunca uses etiquetas <think>. Solo entrega la conclusión y planes.

"""

    system = f"""
Eres {role}. Tu tono es: {tone}

[Guardrails]
{guardrails}

[Estilo de salida]
{style}

[Reglas del agente]
{rules}
{always_rules}

{bsc_block}

{extra}
""".strip()

    return system
