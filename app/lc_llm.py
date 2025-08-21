# app/lc_llm.py
import os
from langchain_ollama import ChatOllama

def get_chat_model():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model    = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
    # Para R1 tenlo frío para que no alucine; sube si necesitas más creatividad
    return ChatOllama(base_url=base_url, model=model, temperature=0.2)
