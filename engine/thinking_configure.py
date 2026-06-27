# engine/thinking_configure.py
from google.genai import types

# Gemini 3.x supports thinking_level; 2.5 and earlier do not.
THINKING_CAPABLE_PREFIX = "gemini-3"

def supports_thinking(model_name: str) -> bool:
    return model_name.lower().startswith(THINKING_CAPABLE_PREFIX)

def get_thinking_config(model_name: str) -> types.ThinkingConfig | None:
    if supports_thinking(model_name):
        return types.ThinkingConfig(thinking_level="high")
    return None