
from utils.config.core import load_config, save_config

def get_thinking_level() -> str:
    config = load_config()
    return config["settings"].get("thinking_level", "high").strip().lower()

def set_thinking_level(level: str) -> None:
    config = load_config()
    config["settings"]["thinking_level"] = level.strip().lower()
    save_config(config)

def get_max_turns() -> int:
    config = load_config()
    return int(config["settings"].get("max_turns", 15))

def set_max_turns(turns: int) -> None:
    config = load_config()
    config["settings"]["max_turns"] = max(1, int(turns))
    save_config(config)

def get_sandbox_settings() -> dict:
    """Timeout limits and hardware allocation limits for Docker sandboxing."""
    config = load_config()
    return config["settings"].get("sandbox", {"memory_limit": "512m", "cpu_limit": 1000000000, "timeout_seconds": 15})

def set_sandbox_settings(memory_limit: str, cpu_limit: int, timeout_seconds: int) -> None:
    config = load_config()
    config["settings"]["sandbox"] = {
        "memory_limit": str(memory_limit),
        "cpu_limit": max(100000, int(cpu_limit)),
        "timeout_seconds": max(1, int(timeout_seconds))
    }
    save_config(config)

def get_max_context_tokens() -> int:
    """Gets the sliding window maximum token threshold for history trimming."""
    config = load_config()
    return int(config["settings"].get("max_context_tokens", 100000))

def set_max_context_tokens(tokens: int) -> None:
    config = load_config()
    config["settings"]["max_context_tokens"] = max(1000, int(tokens))
    save_config(config)

def get_summary_trigger_count() -> int:
    """Trigger background summarization when this many un-summarized messages accumulate."""
    config = load_config()
    return int(config["settings"].get("summary_trigger_count", 30))

def set_summary_trigger_count(count: int) -> None:
    config = load_config()
    config["settings"]["summary_trigger_count"] = max(1, int(count))
    save_config(config)

def get_cli_log_truncation_limit() -> int:
    config = load_config()
    return int(config.get("cli", {}).get("log_truncation_limit", 500))

def set_cli_log_truncation_limit(limit: int) -> None:
    config = load_config()
    if "cli" not in config:
        config["cli"] = {}
    config["cli"]["log_truncation_limit"] = max(10, int(limit))
    save_config(config)

# utils/config/settings.py (Add to bottom)

def get_memory_similarity_threshold() -> float:
    """Minimum cosine similarity required to group a memory into an existing block."""
    config = load_config()
    return float(config["settings"].get("memory_similarity_threshold", 0.80))

def set_memory_similarity_threshold(val: float) -> None:
    config = load_config()
    config["settings"]["memory_similarity_threshold"] = max(0.0, min(float(val), 1.0))
    save_config(config)

def get_api_retry_settings() -> dict:
    """Attempts and delay parameters for handling network timeouts or rate-limits (429s)."""
    config = load_config()
    return config["settings"].get("api_retry", {
        "max_attempts": 3,
        "base_delay": 2.0
    })

def set_api_retry_settings(max_attempts: int, base_delay: float) -> None:
    config = load_config()
    config["settings"]["api_retry"] = {
        "max_attempts": max(1, int(max_attempts)),
        "base_delay": max(0.1, float(base_delay))
    }
    save_config(config)

def get_loop_guard() -> dict:
    """Gets the loop guard thresholds for catching repeating or failing tool runs."""
    config = load_config()
    return config["settings"].get("loop_guard", {
        "max_failed_attempts": 3, 
        "max_success_attempts": 2
    })

def set_loop_guard(max_failed: int | None, max_success: int | None) -> None:
    """Saves the loop guard thresholds securely to the configuration file."""
    config = load_config()
    
    # Store positive integers, or None to trigger the fallback logic
    config["settings"]["loop_guard"] = {
        "max_failed_attempts": int(max_failed) if (max_failed is not None and int(max_failed) > 0) else None,
        "max_success_attempts": int(max_success) if (max_success is not None and int(max_success) > 0) else None
    }
    save_config(config)

def get_system_instruction() -> str | None:
    return load_config()["settings"].get("system_instruction")

def set_system_instruction(instruction: str | None) -> None:
    config = load_config()
    config["settings"]["system_instruction"] = instruction.strip() if instruction and instruction.strip() else None
    save_config(config)

def get_workspace_path() -> str:
    path = load_config()["settings"].get("sandbox", {}).get("workspace_path", "~/.local_workflow_agent/workspace")
    import os
    return os.path.abspath(os.path.expanduser(path))

def set_workspace_path(path: str) -> None:
    config = load_config()
    config["settings"]["sandbox"]["workspace_path"] = path.strip()
    save_config(config)

def get_docker_image() -> str:
    return load_config()["settings"].get("sandbox", {}).get("docker_image", "python:3.11-slim")

def set_docker_image(image: str) -> None:
    config = load_config()
    config["settings"]["sandbox"]["docker_image"] = image.strip()
    save_config(config)