# llm_doctor.py
import os, json, traceback
from pathlib import Path
from dotenv import load_dotenv

def main():
    # Cargar .env
    load_dotenv()

    # Asegurar que Python vea el paquete 'app'
    import sys
    sys.path.insert(0, str(Path.cwd()))

    print("📦 CWD:", Path.cwd())
    api_key = os.getenv("OPENAI_API_KEY")
    print("🔑 OPENAI_API_KEY presente:", bool(api_key))
    if api_key:
        print("   (inicio):", api_key[:8] + "...")
    print("🔧 OPENAI_MODEL:", os.getenv("OPENAI_MODEL", "(no definido)"))

    try:
        from app.lc_llm import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage
    except Exception as e:
        print("❌ No se pudieron importar dependencias:")
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
        SystemMessage(content="Eres un asistente de prueba. Responde SOLO en JSON válido."),
        HumanMessage(content='Responde con {"ok": true}'),
    ]

    try:
        resp = llm.invoke(msgs)
        content = getattr(resp, "content", resp)
        print("\n✅ Respuesta del LLM:")
        print(content if isinstance(content, str) else str(content))

        try:
            parsed = json.loads(content)
            print("\n🧪 JSON parseado OK:", parsed)
            return 0
        except Exception:
            print("\nℹ️ El modelo respondió pero no fue JSON puro.")
            return 0
    except Exception:
        print("\n❌ Error invocando al LLM:")
        traceback.print_exc()
        return 4

if __name__ == "__main__":
    raise SystemExit(main())
