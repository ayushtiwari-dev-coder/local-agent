# """
# BACKUP: DOCKER GETTERS & SETTERS
# -----------------------------------------------------------------
# Cut from `utils/config/settings.py` to keep active configuration pure-local.
# """
# from utils.config.core import load_config, save_config

# def get_max_active_containers() -> int:
#     config = load_config()
#     return int(config["settings"].get("sandbox", {}).get("max_active_containers", 3))

# def set_max_active_containers(count: int) -> None:
#     config = load_config()
#     if "sandbox" not in config["settings"]:
#         config["settings"]["sandbox"] = {}
#     config["settings"]["sandbox"]["max_active_containers"] = max(1, int(count))
#     save_config(config)

# def get_max_total_containers() -> int:
#     config = load_config()
#     return int(config["settings"].get("sandbox", {}).get("max_total_containers", 10))

# def set_max_total_containers(count: int) -> None:
#     config = load_config()
#     if "sandbox" not in config["settings"]:
#         config["settings"]["sandbox"] = {}
#     config["settings"]["sandbox"]["max_total_containers"] = max(1, int(count))
#     save_config(config)

# def get_container_idle_timeout() -> float:
#     config = load_config()
#     return float(config["settings"].get("sandbox", {}).get("container_idle_timeout_minutes", 30.0))

# def set_container_idle_timeout(minutes: float) -> None:
#     config = load_config()
#     if "sandbox" not in config["settings"]:
#         config["settings"]["sandbox"] = {}
#     config["settings"]["sandbox"]["container_idle_timeout_minutes"] = max(0.1, float(minutes))
#     save_config(config)

# def get_docker_image() -> str:
#     return load_config()["settings"].get("sandbox", {}).get("docker_image", "python:3.11-slim")

# def set_docker_image(image: str) -> None:
#     config = load_config()
#     config["settings"]["sandbox"]["docker_image"] = image.strip()
#     save_config(config)

# def set_sandbox_limits_docker(memory_limit: str, cpu_limit: int, timeout_seconds: int) -> None:
#     config = load_config()
#     config["settings"]["sandbox"].update({
#         "memory_limit": str(memory_limit),
#         "cpu_limit": max(100000, int(cpu_limit)),
#         "timeout_seconds": max(1, int(timeout_seconds))
#     })
#     save_config(config)