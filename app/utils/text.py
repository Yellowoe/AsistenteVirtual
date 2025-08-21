# app/utils/text.py
import re

_THINK_FULL = re.compile(r"<think\b[^>]*>.*?</think>", flags=re.IGNORECASE|re.DOTALL)
_THINK_OPEN = re.compile(r"<think\b[^>]*>.*\Z", flags=re.IGNORECASE|re.DOTALL)

def strip_think(text: str) -> str:
    if not text:
        return ""
    s = _THINK_FULL.sub("", text)
    s = _THINK_OPEN.sub("", s)
    return s.strip()
