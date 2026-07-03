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

    # 1. Exact-arg repeat check (catches identical calls - REAL infinite loops)
    # CHANGED: Now only counts BACK-TO-BACK consecutive identical calls.
    total_identical_calls = 0
    failed_identical_calls = 0

    for call in reversed(tool_call_history):
        if call['name'] == tool_name and call['args_json'] == serialized_args:
            total_identical_calls += 1
            if call.get('status') == 'error':
                failed_identical_calls += 1
        else:
            break

    # Halt if it keeps trying the exact same failed action blindly (back-to-back)
    if failed_identical_calls >= 3:
        return True, f"Error: Halting. '{tool_name}' already failed consecutively with these exact params: {tool_args}.", serialized_args

    # Halt if it keeps repeating an action that already succeeded (back-to-back) (wasting tokens)
    if total_identical_calls >= 2:
        return True, f"Error: Halting. '{tool_name}' already succeeded consecutively with these exact params: {tool_args}.", serialized_args

    return False, None, serialized_args