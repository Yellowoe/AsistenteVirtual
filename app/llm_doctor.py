# llm_doctor.py
import os, json, traceback
from pathlib import Path

def main():
    # Para que Python vea el paquete 'app'
    import sys
    sys.path.insert(0, str(Path.cwd()))

    print("📦 CWD:", Path.cwd())
    print("🔑 OPENAI_API_KEY presente:", bool(os.getenv("OPENAI_API_KEY")))
    print("🔧 OPENAI_MODEL:", os.getenv("OPENAI_MODEL", "(no definido)"))

    try:
        from app.lc_llm import get_chat_model
        from app.tools.prompting import build_system_prompt
    except Exception as e:
        print("❌ No se pudieron importar get_chat_model/build_system_prompt:")
        traceback.print_exc()
        return 2

    try:
        llm = get_chat_model()
        model_name = getattr(llm, "model_name", getattr(llm, "model", "(desconocido)"))
        print("🤖 Modelo cargado:", model_name)
    except Exception:
        print("❌ Error creando el modelo:")
        traceback.print_exc()
        return 3

    msgs = [
        {"role": "system", "content": build_system_prompt("av_gerente")},
        {"role": "user", "content": 'Responde SOLO con JSON válido: {"ok": true}'},
    ]

    try:
        resp = llm.invoke(msgs)
        content = getattr(resp, "content", resp)
        print("\n✅ Respuesta del LLM:")
        print(content if isinstance(content, str) else str(content))
        # Intento parsear por si cumple
        try:
            parsed = json.loads(content)
            print("\n🧪 JSON parseado OK:", parsed)
            return 0
        except Exception:
            print("\nℹ️ El modelo respondió pero no fue JSON puro (lo cual es aceptable para esta prueba).")
            return 0
    except Exception:
        print("\n❌ Error invocando al LLM:")
        traceback.print_exc()
        return 4

if __name__ == "__main__":
    raise SystemExit(main())
