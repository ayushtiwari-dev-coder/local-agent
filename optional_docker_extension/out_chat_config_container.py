# """
# BACKUP: OUT-OF-CHAT HEADLESS DOCKER CONTROLLERS
# -----------------------------------------------------------------
# Cut from `config_configure/out_chat_config.py`.
# """
# import utils.config_manager as config_manager

# def update_max_active_containers(count: int) -> dict:
#     try:
#         config_manager.set_max_active_containers(count)
#         return {"status": "success", "message": f"Maximum concurrent running containers successfully updated to {count}."}
#     except Exception as e:
#         return {"status": "error", "message": f"Failed to update active container limit: {e}"}

# def update_max_total_containers(count: int) -> dict:
#     try:
#         config_manager.set_max_total_containers(count)
#         return {"status": "success", "message": f"Total container storage limit successfully updated to {count}."}
#     except Exception as e:
#         return {"status": "error", "message": f"Failed to update storage limit: {e}"}

# def update_container_idle_timeout(minutes: float) -> dict:
#     try:
#         config_manager.set_container_idle_timeout(minutes)
#         return {"status": "success", "message": f"Container idle auto-stop threshold successfully updated to {minutes} minutes."}
#     except Exception as e:
#         return {"status": "error", "message": f"Failed to update idle timeout thresholds: {e}"}

# def update_docker_image(image: str) -> dict:
#     try:
#         config_manager.set_docker_image(image)
#         return {"status": "success", "message": "Docker image updated successfully."}
#     except Exception as e:
#         return {"status": "error", "message": f"Failed to update Docker image: {e}"}

# def update_sandbox_limits(memory_limit: str, timeout_seconds: int, cpu_limit: int = 1000000000) -> dict:
#     try:
#         config_manager.set_sandbox_settings_docker(memory_limit, cpu_limit, timeout_seconds)
#         return {"status": "success", "message": "Sandbox safety bounds updated successfully!"}
#     except Exception as e:
#         return {"status": "error", "message": f"Failed to update sandbox limits: {e}"}