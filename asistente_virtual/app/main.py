import json
from .router import Router
from .state import GlobalState

def main():
    router = Router(default_agent="av_gerente")
    state = GlobalState(period="2025-08")

    task = {"payload": {
        "question": "Quiero un resumen ejecutivo de agosto con CxC y CxP.",
        "period": "2025-08"
    }}
    result = router.dispatch(task, state)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
