import json

def check_for_infinite_loop(
    tool_call_history: list[dict], 
    tool_name: str, 
    tool_args: dict
) -> tuple[bool, str | None, str]:
    """
    Checks if the proposed tool execution is stuck in a hallucination or failure loop.
    
    Returns:
        is_looping (bool): True if a loop is detected.
        error_message (str | None): The formatted error message if True, otherwise None.
        serialized_args (str): The serialized JSON string of the tool arguments.
    """
    # Serialize arguments with sorted keys for consistent hashing/string matching
    serialized_args = json.dumps(tool_args, sort_keys=True)
    
    # 1. Count identical calls
    total_identical_calls = sum(
        1 for call in tool_call_history 
        if call['name'] == tool_name and call['args_json'] == serialized_args
    )
    
    # 2. Count failed identical calls
    failed_identical_calls = sum(
        1 for call in tool_call_history 
        if call['name'] == tool_name and call['args_json'] == serialized_args and call['status'] == 'error'
    )
    
    # Case A: Halting on 3rd attempt of a known failing action
    if failed_identical_calls >= 2:
        error_msg = (
            f"Error: Halting execution. The agent is stuck in an error loop, trying to run "
            f"'{tool_name}' with identical failing parameters for the 3rd time: {tool_args}."
        )
        return True, error_msg, serialized_args
    
    # Case B: Halting on 4th attempt of a known successful action
    if total_identical_calls >= 3:
        error_msg = (
            f"Error: Halting execution. The agent is repeating the exact same successful tool call "
            f"without making progress: '{tool_name}' with parameters {tool_args}."
        )
        return True, error_msg, serialized_args
    
    return False, None, serialized_args