# app/llm.py
import os, re, requests

DEFAULT_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT_SEC", "600"))
DEFAULT_MODEL   = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
BASE_URL        = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Expresiones regulares para limpiar <think>
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", flags=re.IGNORECASE | re.DOTALL)
_THINK_OPEN_TO_EOF_RE = re.compile(r"<think\b[^>]*>.*\Z", flags=re.IGNORECASE | re.DOTALL)

def strip_think(text: str) -> str:
    """Elimina bloques <think>...</think> del texto"""
    s = text or ""
    s = _THINK_BLOCK_RE.sub("", s)
    s = _THINK_OPEN_TO_EOF_RE.sub("", s)
    return s.strip()

class LLM:
    def __init__(self, base_url=None, model=None, timeout=None):
        self.base_url = base_url or BASE_URL
        self.model    = model or DEFAULT_MODEL
        self.timeout  = timeout or DEFAULT_TIMEOUT

    def chat(self, system: str, user: str) -> str:
        """Envía prompt al modelo vía Ollama y devuelve la respuesta limpia"""
        payload = {
            "model":  self.model,
            "system": system,
            "prompt": user,
            "stream": False
        }
        r = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=self.timeout)
        r.raise_for_status()
        raw = r.json().get("response", "")
        return strip_think(raw)
