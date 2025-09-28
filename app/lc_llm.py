# app/lc_llm.py
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Cargar variables de entorno desde .env
load_dotenv()

def get_chat_model():
    """
    Devuelve el modelo GPT-4o (completo) para tareas de análisis financiero y causalidad.
    Configurado con variables de entorno:
      - OPENAI_API_KEY (obligatorio)
      - OPENAI_MODEL (por defecto 'gpt-4o')
      - OPENAI_TEMPERATURE (por defecto 0)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta la variable OPENAI_API_KEY")

    model = os.getenv("OPENAI_MODEL", "gpt-4o")  # ahora el grande por defecto
    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0"))

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key
    )
