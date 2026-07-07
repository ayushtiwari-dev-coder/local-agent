# import os
# import logging
# import shlex
# import docker
# import utils.config_manager as config_manager
# # Import dynamic lifecycle routines
# from optional_docker_extension.sandbox_lifecycle import enforce_sandbox_lifecycle_policy
# import time

# logger = logging.getLogger("tools.sandbox_executor")

# class DockerSandboxExecutor:
#     def __init__(self, sandbox_root: str):
#         self.sandbox_root = os.path.abspath(sandbox_root)
#         self._cached_client = None

#     def _get_docker_client_with_retry(self) -> docker.DockerClient:
#         """
#         Attempts to connect to the local Docker daemon.
#         Retries up to 3 times with exponential backoff (1s, 2s, 4s delays).
#         """
        
#         if self._cached_client is not None:
#             try:
#                 self._cached_client.ping()
#                 return self._cached_client
#             except Exception:
#                 self._cached_client = None

#         retry_delays = [1, 2, 4]
#         last_error = None

#         for idx, delay in enumerate(retry_delays):
#             try:
#                 client = docker.from_env()
#                 client.ping()
#                 self._cached_client = client
#                 return client
#             except Exception as e:
#                 last_error = e
#                 logger.warning(
#                     f"Docker connection check failed (Attempt {idx + 1}/3). "
#                     f"Retrying in {delay} seconds... Error: {e}"
#                 )
#                 time.sleep(delay)

#         raise RuntimeError(f"Connection failed due to this error: {last_error}")

#     def run_command(self, command: str, timeout_seconds: int = None, conversation_id: int = None) -> dict:
#         """
#         Executes terminal commands inside custom-configured, persistent Docker sandboxes.
#         """


#         # Retrieve system properties from configuration getters
#         sandbox_config = config_manager.get_sandbox_settings()
#         docker_image = config_manager.get_docker_image()
#         workspace_path = config_manager.get_workspace_path()

#         if timeout_seconds is None:
#             timeout_seconds = sandbox_config.get("timeout_seconds", 15)

#         # 1. Establish connection to Docker daemon
#         try:
#             client = self._get_docker_client_with_retry()
#         except Exception as conn_error:
#             return {
#                 "status": "error",
#                 "output": f"Connection failed due to this error: {conn_error}"
#             }

#         # 2. ENFORCE THE SELF-HEALING LIFECYCLE CONTROLS
#         # Pass conversation_id to protect the active sandbox during multitasking constraints
#         enforce_sandbox_lifecycle_policy(client, conversation_id)

#         # 3. Resolve container namespace mappings
#         if conversation_id is not None:
#             container_name = f"local_agent_sandbox_conv_{conversation_id}"
#         else:
#             container_name = "local_agent_sandbox_default"

#         # 4. Locate or initialize the container
#         try:
#             container = client.containers.get(container_name)
#             if container.status != "running":
#                 container.start()
#         except docker.errors.NotFound:
#             try:
#                 logger.info(f"Creating persistent workspace sandbox container: {container_name}")
#                 container = client.containers.run(
#                     image=docker_image,
#                     command="tail -f /dev/null",
#                     name=container_name,
#                     detach=True,
#                     tty=True,
#                     volumes={workspace_path: {"bind": "/workspace", "mode": "rw"}},
#                     working_dir="/workspace",
#                     network_disabled=True,
#                     mem_limit=sandbox_config.get("mem_limit", "512m"),
#                     nano_cpus=sandbox_config.get("nano_cpus", 1000000000),
#                 )
#             except Exception as creation_error:
#                 return {
#                     "status": "error",
#                     "output": f"Failed to initialize sandbox container '{container_name}': {creation_error}"
#                 }

#         # 5. Execute command inside isolation context
#         try:
#             execution_cmd = f"sh -c {shlex.quote(command)}"
#             exec_result = container.exec_run(
#                 cmd=execution_cmd,
#                 workdir="/workspace",
#                 demux=False
#             )
            
#             exit_code = exec_result.exit_code
#             output_text = exec_result.output.decode("utf-8").strip() or "[Command executed with no output]"
            
#             if exit_code == 0:
#                 return {"status": "success", "output": output_text}
#             else:
#                 return {
#                     "status": "error",
#                     "output": f"Error: Process failed with exit code {exit_code}. Output:\n{output_text}"
#                 }

#         except Exception as exec_error:
#             return {
#                 "status": "error",
#                 "output": f"Sandbox execution failure inside container '{container_name}': {exec_error}"
#             }

#     def cleanup_container(self, conversation_id: int) -> bool:
#         """Safely stops and removes a persistent container during manual deletion."""
#         try:
#             client = self._get_docker_client_with_retry()
#             container_name = f"local_agent_sandbox_conv_{conversation_id}"
#             try:
#                 container = client.containers.get(container_name)
#                 logger.info(f"Manual purge of sandbox container: {container_name}")
#                 container.stop(timeout=5)
#                 container.remove(v=True)
#                 return True
#             except docker.errors.NotFound:
#                 return True
#         except Exception as e:
#             logger.warning(f"Failed to clean up sandbox container for conversation {conversation_id}: {e}")
#             return False

#fully written docker logic for sandbox executer,this will be used to run command 