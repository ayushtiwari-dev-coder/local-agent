# FILE: utils/config_manager.py
import os
import json
from database.connection import APP_DIR

CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "providers": {
        "gemini": {
            "api_key": None,
            "active_model": "gemini-3.1-flash-lite"
        },
        "groq": {
            "api_key": None,
            "active_model": "llama-3.3-70b-versatile"
        }
    },
    "default_provider": "gemini",
    "thinking_level": "high",
    
    "orchestra": {
        "manager": {"provider": "gemini", "model": "gemini-3.1-flash-lite"},
        "planner": {"provider": "gemini", "model": "gemini-3.1-flash-lite"},
        "executor": {"provider": "gemini", "model": "gemini-3.1-flash-lite"}
    }
}


def load_config() -> dict:
    """Loads the config dictionary, fallback to defaults if file does not exist or is corrupted."""
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            # Ensure basic structure compatibility
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(user_config)
            return merged_config
    except Exception:
        # If config is corrupted, fall back safely to avoid crashing startup
        return DEFAULT_CONFIG

def save_config(config: dict) -> None:
    """Saves the config dictionary locally to ~/.local_workflow_agent/config.json."""
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"\n[Warning] Failed to save local configuration: {e}")

def get_provider_api_key(provider_name: str) -> str | None:
    """Gets the API key for a provider, falling back to environment variable if not in config."""
    config = load_config()
    provider_name = provider_name.strip().lower()
    
    # Check config first
    key = config.get("providers", {}).get(provider_name, {}).get("api_key")
    if key:
        return key
    
    # Fallback to system environment variable (maintains backward compatibility)
    env_var_map = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY"
    }
    return os.environ.get(env_var_map.get(provider_name, ""))

def set_provider_api_key(provider_name: str, api_key: str | None) -> None:
    """Saves the API key for a specified provider."""
    config = load_config()
    provider_name = provider_name.strip().lower()
    if "providers" not in config:
        config["providers"] = {}
    if provider_name not in config["providers"]:
        config["providers"][provider_name] = {}
        
    config["providers"][provider_name]["api_key"] = api_key
    save_config(config)

def get_active_model(provider_name: str) -> str:
    """Gets the active selected model for a provider."""
    config = load_config()
    provider_name = provider_name.strip().lower()
    return config.get("providers", {}).get(provider_name, {}).get("active_model", "gemini-3.1-flash-lite")

def set_active_model(provider_name: str, model_name: str) -> None:
    """Sets the active selected model for a provider."""
    config = load_config()
    provider_name = provider_name.strip().lower()
    if "providers" not in config:
        config["providers"] = {}
    if provider_name not in config["providers"]:
        config["providers"][provider_name] = {}
        
    config["providers"][provider_name]["active_model"] = model_name
    save_config(config)

def get_default_provider() -> str:
    """Gets the configured default provider."""
    config = load_config()
    return config.get("default_provider", "gemini")

def set_default_provider(provider_name: str) -> None:
    """Sets the default provider."""
    config = load_config()
    config["default_provider"] = provider_name.strip().lower()
    save_config(config)

def get_thinking_level() -> str:
    """Gets the globally preferred thinking level (low, medium, high, off)."""
    config = load_config()
    return config.get("thinking_level", "high").strip().lower()

def set_thinking_level(level: str) -> None:
    """Sets the globally preferred thinking level."""
    config = load_config()
    config["thinking_level"] = level.strip().lower()
    save_config(config)

def is_provider_configured(provider_name: str) -> bool:
    """Checks if a provider has a valid key saved or in environment variables."""
    return bool(get_provider_api_key(provider_name))

def has_any_provider_configured() -> bool:
    """Returns True if at least one provider has configured keys."""
    return is_provider_configured("gemini") or is_provider_configured("groq")

def get_orchestra_route(role_name: str) -> dict:
    """
    Retrieves the configured provider and model routing for a specific agent role.
    Falls back to the default Gemini configuration if the route is missing.
    """
    config = load_config()
    orchestra = config.get("orchestra", DEFAULT_CONFIG["orchestra"])
    return orchestra.get(
        role_name, 
        {"provider": "gemini", "model": "gemini-3.1-flash-lite"}
    )
# Append to the bottom of utils/config_manager.py
def set_orchestra_route(role_name: str, provider_name: str, model_name: str) -> None:
    """Saves custom routing properties (Provider + Model) for specialized Agent roles."""
    config = load_config()
    if "orchestra" not in config:
        config["orchestra"] = {}
    config["orchestra"][role_name] = {
        "provider": provider_name.strip().lower(),
        "model": model_name.strip()
    }
    save_config(config)