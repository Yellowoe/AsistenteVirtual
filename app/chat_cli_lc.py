# app/chat_cli_lc.py
import json, time, os
from pathlib import Path
from datetime import datetime
from app.graph_lc import run_query

def main():
    print("💬 Chat AV Gerente (LangChain). Escribe tu pregunta (o 'salir').\n")
    period = "2025-08"

    # Crear carpeta logs si no existe
    log_dir = Path(__file__).resolve().parents[1] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_name = log_dir / f"chat_lc_log_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    history = []

    try:
        while True:
            q = input("Tú: ").strip()
            if not q:
                continue
            if q.lower() in {"salir", "exit", "quit"}:
                break

            t0 = time.time()
            try:
                result = run_query(q, period)
                dt = round(time.time() - t0, 2)
                print(f"\n⏱️ {dt}s")

                intent = result.get("intent")
                if intent:
                    print(f"🔎 Intent: {intent}")

                gerente = result.get("gerente")
                if gerente and gerente.get("executive_decision_bsc"):
                    print("\n📄 Resumen ejecutivo:")
                    print(gerente["executive_decision_bsc"])
                else:
                    trace = result.get("trace", [])
                    print("\n📊 Resultado:")
                    print(json.dumps(trace[-1] if trace else result, ensure_ascii=False, indent=2))

                history.append({"q": q, "result": result})
            except Exception as e:
                print(f"⚠️ Error: {e}")

    except KeyboardInterrupt:
        pass
    finally:
        with open(log_name, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"\n📝 Log guardado en {log_name}")

if __name__ == "__main__":
    main()
