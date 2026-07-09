# tools/core.py
from typing import Callable

def agent_tool(func: Callable) -> Callable:
    """
    Decorator that tags a function as an LLM-callable tool.
    The dynamic registry will auto-discover functions with this tag.
    """
    func.__is_agent_tool__ = True
    return func