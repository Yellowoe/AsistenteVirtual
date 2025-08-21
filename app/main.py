# app/main_lc.py
import sys, json
from app.graph_lc import run_query

def main():
    question = " ".join(sys.argv[1:]).strip()
    period = None  # o fija "2025-08" si quieres
    out = run_query(question, period)
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
