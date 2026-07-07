# import logging
# import docker
# from datetime import datetime, timezone

# # Database and configuration modules
# from database.helper import execute_read
# import utils.config_manager as config_manager

# logger = logging.getLogger("tools.sandbox_lifecycle")


# def get_conversation_sandboxes(client: docker.DockerClient) -> list[tuple[int, docker.models.containers.Container]]:
#     """
#     Scans the local Docker host and filters containers matching the agent naming pattern.
#     Returns a list of tuples containing (conversation_id, Container_object).
#     """
#     try:
#         all_containers = client.containers.list(all=True)
#     except Exception as e:
#         logger.error(f"Failed to query container list from Docker daemon: {e}")
#         return []

#     agent_sandboxes = []
#     for container in all_containers:
#         if container.name.startswith("local_agent_sandbox_conv_"):
#             try:
#                 # Extract conversation ID suffix
#                 conv_id = int(container.name.split("_")[-1])
#                 agent_sandboxes.append((conv_id, container))
#             except ValueError:
#                 continue
#     return agent_sandboxes


# def _get_container_last_active_time(container: docker.models.containers.Container, conversation_id: int) -> datetime:
#     """
#     Retrieves the last execution timestamp inside SQLite for this conversation.
#     Falls back to the container's creation metadata if no executions have occurred yet.
#     """
#     now_utc = datetime.now(timezone.utc)
    
#     try:
#         query = """
#             SELECT created_at FROM tool_logs 
#             WHERE conversation_id = ? 
#             ORDER BY id DESC LIMIT 1;
#         """
#         row = execute_read(query, (conversation_id,), fetch_one=True)
        
#         if row and row.get("created_at"):
#             ts_str = row["created_at"].strip()
#             if "." in ts_str:
#                 ts_str = ts_str.split(".")[0]
#             dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
#             return dt.replace(tzinfo=timezone.utc)
            
#     except Exception as db_err:
#         logger.warning(f"Failed to query database last active time for conversation {conversation_id}: {db_err}")

#     # Fallback: Container creation ISO8601 timestamp
#     try:
#         created_raw = container.attrs.get("Created", "")
#         if created_raw:
#             clean_iso = created_raw.split(".")[0].replace("Z", "")
#             dt = datetime.strptime(clean_iso, "%Y-%m-%dT%H:%M:%S")
#             return dt.replace(tzinfo=timezone.utc)
#     except Exception as container_err:
#         logger.warning(f"Failed to parse container creation time: {container_err}")

#     return now_utc


# def enforce_sandbox_lifecycle_policy(client: docker.DockerClient, active_conversation_id: int = None) -> None:
#     """
#     Orchestrates the multitasking constraints, stopping idle containers and 
#     pruning older disk layers (LRU) based on user-defined configurations.
#     """
#     # Load settings directly from user-controlled config manager
#     max_active = config_manager.get_max_active_containers()
#     max_total = config_manager.get_max_total_containers()
#     idle_timeout_mins = config_manager.get_container_idle_timeout()
    
#     now_utc = datetime.now(timezone.utc)
#     sandboxes = get_conversation_sandboxes(client)
#     if not sandboxes:
#         return

#     # Extract metadata properties for sorting and comparisons
#     enriched_sandboxes = []
#     for conv_id, container in sandboxes:
#         last_active = _get_container_last_active_time(container, conv_id)
#         enriched_sandboxes.append({
#             "conv_id": conv_id,
#             "container": container,
#             "status": container.status,
#             "last_active": last_active,
#             "idle_duration_secs": (now_utc - last_active).total_seconds()
#         })

#     # Sort all sandboxes oldest-activity first
#     enriched_sandboxes.sort(key=lambda x: x["last_active"])

#     # 1. Idle Timeout Auto-Stop (RAM Preservation)
#     active_name = f"local_agent_sandbox_conv_{active_conversation_id}" if active_conversation_id else None
    
#     for s in enriched_sandboxes:
#         # Never auto-stop the container actively executing the current command
#         if s["container"].name != active_name and s["status"] == "running":
#             idle_minutes = s["idle_duration_secs"] / 60.0
#             if idle_minutes > idle_timeout_mins:
#                 logger.info(f"Idle Guard: Stopping inactive container {s['container'].name} (Idle for {idle_minutes:.1f}m)")
#                 try:
#                     s["container"].stop(timeout=2)
#                     s["status"] = "exited"
#                 except Exception as stop_err:
#                     logger.warning(f"Failed to auto-stop idle container {s['container'].name}: {stop_err}")

#     # 2. Concurrency Capacity Throttle (Multitasking Slot Guard)
#     active_containers = [s for s in enriched_sandboxes if s["status"] == "running"]
#     if len(active_containers) > max_active:
#         excess_active_count = len(active_containers) - max_active
#         # Stops oldest running containers first
#         for i in range(excess_active_count):
#             target = active_containers[i]
#             # Ensure the actively executed task container is never forcefully throttled
#             if target["container"].name != active_name:
#                 logger.info(f"Concurrency Guard: Stopping container {target['container'].name} to free run slot.")
#                 try:
#                     target["container"].stop(timeout=2)
#                     target["status"] = "exited"
#                 except Exception as e:
#                     logger.warning(f"Failed to stop container {target['container'].name}: {e}")

#     # 3. Disk Retention Capacity Limits (Disk Space Pruning Guard)
#     sandboxes_on_disk = get_conversation_sandboxes(client)
#     if len(sandboxes_on_disk) > max_total:
#         enriched_all = []
#         for conv_id, container in sandboxes_on_disk:
#             enriched_all.append({
#                 "container": container,
#                 "last_active": _get_container_last_active_time(container, conv_id)
#             })
#         enriched_all.sort(key=lambda x: x["last_active"])
        
#         excess_total_count = len(enriched_all) - max_total
#         for i in range(excess_total_count):
#             target_container = enriched_all[i]["container"]
#             # Guard the active session container from being removed from disk
#             if target_container.name != active_name:
#                 logger.info(f"Disk Guard: Hard limit ({max_total}) exceeded. Pruning container: {target_container.name}")
#                 try:
#                     target_container.stop(timeout=2)
#                     target_container.remove(v=True)
#                 except Exception as e:
#                     logger.warning(f"Failed to prune cold storage layer {target_container.name}: {e}")


#cannot use myself since it is docker and my computer cannot run docker(anyone who wants to run than just import stuff in sandbox executer file)