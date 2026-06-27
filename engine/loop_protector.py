import json

def _extract_paths(tool_name: str, tool_args: dict) -> set[str] | None:
    """For file tools, pull out the set of file paths being touched, regardless of content."""
    if tool_name == "write_files":
        raw = tool_args.get("files_json")
        try:
            files = json.loads(raw) if isinstance(raw, str) else raw
            return {f["path"] for f in files if isinstance(f, dict) and "path" in f}
        except Exception:
            return None
    if tool_name == "read_files":
        raw = tool_args.get("paths_json")
        try:
            paths = json.loads(raw) if isinstance(raw, str) else raw
            return set(paths) if isinstance(paths, list) else None
        except Exception:
            return None
    return None


def check_for_infinite_loop(
    tool_call_history: list[dict], tool_name: str, tool_args: dict
) -> tuple[bool, str | None, str]:
    serialized_args = json.dumps(tool_args, sort_keys=True)

    # 1. Exact-arg repeat check (catches identical calls)
    total_identical_calls = sum(
        1 for call in tool_call_history
        if call['name'] == tool_name and call['args_json'] == serialized_args
    )
    failed_identical_calls = sum(
        1 for call in tool_call_history
        if call['name'] == tool_name and call['args_json'] == serialized_args and call['status'] == 'error'
    )
    if failed_identical_calls >= 1:
        return True, f"Error: Halting. '{tool_name}' already failed once with these exact params: {tool_args}.", serialized_args
    if total_identical_calls >= 1:
        return True, f"Error: Halting. '{tool_name}' already succeeded once with these exact params: {tool_args}.", serialized_args

    # 2. Path-level repeat check (catches "same file, different content" loops)
    current_paths = _extract_paths(tool_name, tool_args)
    if current_paths:
        same_path_calls = sum(
            1 for call in tool_call_history
            if call['name'] == tool_name
            and (call.get('paths') and call['paths'] & current_paths)
        )
        if same_path_calls >= 1:
            return True, (
                f"Error: Halting. '{tool_name}' has already touched {current_paths} once this turn. "
                f"Re-running on the same file(s) with different content is not allowed without explicit instruction."
            ), serialized_args

    return False, None, serialized_args