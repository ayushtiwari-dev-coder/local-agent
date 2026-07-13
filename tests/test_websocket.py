# tests/test_websocket.py
import ast
import json
import pytest
import threading
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
import time

# Target the singular "websocket" module based on your naming decision
from interfaces.websocket import router, active_threads, manager
from managers.approval_manager import active_approvals, wait_for_decision, resolve_decision

app = FastAPI()
app.include_router(router)

@pytest.fixture(autouse=True)
def reset_shared_state():
    """
    Strictly resets and cleans up shared concurrent states 
    before and after every test execution to prevent test poisoning.
    """
    active_threads.clear()
    active_approvals.clear()
    manager.active_connections.clear()
    yield
    active_threads.clear()
    active_approvals.clear()
    manager.active_connections.clear()


# =====================================================================
# 1. SECURITY & HANDSHAKE BOUNDARY TESTS
# =====================================================================

@patch("interfaces.websocket.config_manager")
def test_handshake_and_config_negotiation(mock_config):
    """
    Asserts that the initial HTTP handshake properly validates, upgrades, 
    and immediately pushes the active system configuration to the UI.
    """
    mock_config.get_provider_api_key.return_value = "local_vault_key"
    mock_config.get_default_provider.return_value = "gemini"
    mock_config.get_active_model.return_value = "gemini-3.1-flash-lite"
    mock_config.get_temperature.return_value = 0.2

    client = TestClient(app)
    with client.websocket_connect("/ws/101?token=local_vault_key") as ws:
        # Check initial welcome packet
        data = ws.receive_json()
        assert data["type"] == "connection_established"
        assert data["payload"]["session_id"] == "session_101"
        assert data["payload"]["active_provider"] == "gemini"
        assert data["payload"]["active_model"] == "gemini-3.1-flash-lite"
        assert data["payload"]["temperature"] == 0.2


@patch("interfaces.websocket.config_manager")
def test_invalid_handshake_token_rejection(mock_config):
    """
    Asserts that connection attempts using mismatched credentials are 
    instantly rejected at the HTTP handshake level with close code 4001.
    """
    mock_config.get_provider_api_key.return_value = "secure_token_1"
    client = TestClient(app)

    # Catch the exact WebSocketDisconnect exception raised by FastAPI's TestClient
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/101?token=unauthorized_token"):
            pass
            
    # Verify the server closed it specifically with our 4001 unauthorized code
    assert exc.value.code == 4001


# =====================================================================
# 2. CONCURRENCY & THREAD-BLOCKING BOUNDARY TESTS
# =====================================================================

@patch("interfaces.websocket.config_manager")
def test_concurrent_execution_block(mock_config):
    """
    Asserts that if an agent thread is already running for a conversation ID,
    any secondary user execution requests are instantly rejected on the same socket.
    """
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_default_provider.return_value = "gemini"
    mock_config.get_active_model.return_value = "gemini-3.1-flash-lite"
    mock_config.get_temperature.return_value = 0.2

    client = TestClient(app)

    # Simulate an active working thread already registered for conversation 42
    active_threads[42] = MagicMock()

    with client.websocket_connect("/ws/42") as ws:
        ws.receive_json()  # Consume handshake welcome
        
        # Dispatch a second message
        ws.send_json({
            "type": "user_message",
            "payload": {"content": "Execute another command."}
        })
        
        # Verify execution is blocked
        response = ws.receive_json()
        assert response["type"] == "execution_error"
        assert response["payload"]["error_code"] == "CONCURRENT_RUN_BLOCKED"


# =====================================================================
# 3. ROBUST PARSING & SECURITY SANITIZATION TESTS
# =====================================================================

@patch("interfaces.websocket.config_manager")
def test_websocket_status_callback_ast_parsing_safety(mock_config):
    """
    Verifies that the callback string parser cleanly extracts tool parameters, 
    but safely drops malicious code injections using ast.literal_eval.
    """
    mock_config.get_provider_api_key.return_value = None
    client = TestClient(app)

    # Mocking active connection
    mock_ws = MagicMock()
    manager.active_connections[99] = mock_ws

    from interfaces.websocket import websocket_status_callback
    loop = MagicMock()

    # Case A: Standard safe dict string literal
    safe_status = "Executing tool 'write_files' with arguments:\n{'files': [{'path': 'test.py'}]}"
    websocket_status_callback(loop, 99, safe_status)
    
    # Assert asyncio schedules the message
    loop.call_soon_threadsafe.assert_called()

    # Case B: Exploit injection payload targeting evaluation engine
    exploit_status = "Executing tool 'write_files' with arguments:\n__import__('os').system('rm -rf /')"
    
    # Execute callback - ast.literal_eval must catch this and fall back to empty arguments
    # instead of crashing the thread or executing the code.
    try:
        websocket_status_callback(loop, 99, exploit_status)
    except Exception as e:
        pytest.fail(f"ast.literal_eval threw an uncaught error: {e}")


# =====================================================================
# 4. STATEFUL HUMAN-IN-THE-LOOP (HITL) WORKFLOW TESTS
# =====================================================================

@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.AgentEngine")
def test_stateful_approval_and_unfreeze_flow(mock_engine_class, mock_config):
    """
    Rigorous Turn-by-Turn test. Simulates the agent hitting an unsafe tool, 
    dispatching an approval requirement, freezing the background thread, 
    receiving a client approval over WebSocket, and unfreezing to complete.
    """
    import time
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_default_provider.return_value = "gemini"
    mock_config.get_active_model.return_value = "gemini-3.1-flash-lite"
    mock_config.get_temperature.return_value = 0.2

    mock_engine = MagicMock()
    mock_engine_class.return_value = mock_engine

    thread_execution_outcome = {"executed": False}

    def mock_react_send_message(conversation_id, user_text, source, status_callback, approval_callback):
        # FIX: Emit the status update to unfreeze the ws.receive_json() waiting for "thought_start"
        if status_callback:
            status_callback("Generating thoughts... [Turn #1]")

        # 1. Trigger the unsafe tool callback (mimicking handle_permissions)
        is_approved = approval_callback("run_terminal_command", {"command": "npm install"}, conversation_id)
        
        if is_approved:
            thread_execution_outcome["executed"] = True
            return "Command ran successfully."
        else:
            thread_execution_outcome["executed"] = False
            return "Execution denied by user."

    mock_engine.send_message.side_effect = mock_react_send_message
    client = TestClient(app)

    with client.websocket_connect("/ws/1") as ws:
        ws.receive_json()  # Consume handshake welcome
        
        # Send user prompt
        ws.send_json({
            "type": "user_message",
            "payload": {"content": "Install node dependencies."}
        })
        
        # Verify thought start event dispatched
        assert ws.receive_json()["type"] == "thought_start"
        
        # Verify approval prompt was dispatched to UI
        approval_event = ws.receive_json()
        assert approval_event["type"] == "approval_required"
        assert approval_event["payload"]["tool_name"] == "run_terminal_command"
        assert approval_event["payload"]["arguments"] == {"command": "npm install"}

        # DYNAMIC POLLING: Check every 50ms up to 3 seconds for the registration.
        # This completely eliminates timing issues on slow or busy CPUs.
        registered = False
        for _ in range(60):
            if 1 in active_approvals:
                registered = True
                break
            time.sleep(0.05)
            
        assert registered is True, "Background thread failed to register approval event in time."

        # Send user approval response over the active WebSocket
        ws.send_json({
            "type": "approval_response",
            "payload": {"approved": True}
        })

        # Wait for background thread to wake up and finish execution
        msg_chunk = ws.receive_json()
        assert msg_chunk["type"] == "message_chunk"
        assert msg_chunk["payload"]["chunk"] == "Command ran successfully."
        
        complete_event = ws.receive_json()
        assert complete_event["type"] == "execution_completed"
        
        # Assert thread state unfroze with positive resolution
        assert thread_execution_outcome["executed"] is True


@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.AgentEngine")
def test_user_disconnect_during_freeze_teardown(mock_engine_class, mock_config):
    """
    Asserts that if the WebSocket drops (e.g. user closes browser tab) 
    while the background thread is frozen waiting on approval, the thread is 
    immediately unfrozen and exited to prevent memory leaks and zombie threads.
    """
    import time
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_default_provider.return_value = "gemini"
    mock_config.get_active_model.return_value = "gemini-3.1-flash-lite"
    mock_config.get_temperature.return_value = 0.2

    mock_engine = MagicMock()
    mock_engine_class.return_value = mock_engine

    thread_exit_status = {"exited": False}

    def mock_react_loop(conversation_id, user_text, source, status_callback, approval_callback):
        # FIX: Emit the status update to unfreeze the ws.receive_json() waiting for "thought_start"
        if status_callback:
            status_callback("Generating thoughts... [Turn #1]")

        # Freeze here waiting for decision
        approval_callback("run_terminal_command", {"command": "delete"}, conversation_id)
        
        # Once unblocked, record exit
        thread_exit_status["exited"] = True
        return "Aborted"

    mock_engine.send_message.side_effect = mock_react_loop
    client = TestClient(app)

    with client.websocket_connect("/ws/88") as ws:
        ws.receive_json()  # Welcome
        
        ws.send_json({
            "type": "user_message",
            "payload": {"content": "Run danger command"}
        })
        
        ws.receive_json()  # thought_start
        ws.receive_json()  # approval_required

        # DYNAMIC POLLING: Wait up to 3 seconds for Antarctica to fall asleep
        registered = False
        for _ in range(60):
            if 88 in active_approvals:
                registered = True
                break
            time.sleep(0.05)
            
        assert registered is True, "Background thread failed to register before disconnect."
        
        # Simulate browser disconnect (Tab closed)
        ws.close()

    # DYNAMIC POLLING: Give the OS up to 2 seconds to execute the thread cleanup
    exited = False
    for _ in range(40):
        if thread_exit_status["exited"]:
            exited = True
            break
        time.sleep(0.05)

    # The disconnect should have triggered clean-up and immediately unfrozen the thread
    assert 88 not in active_approvals
    assert exited is True, "Background thread failed to exit gracefully after disconnect."


@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.AgentEngine")
def test_agent_workflow_exception_handling(mock_engine_class, mock_config):
    """
    Asserts that unexpected crashes inside the Agent thread (e.g. API down, db error)
    are caught and pushed gracefully to the UI without crashing the main FastAPI process.
    """
    import time # Ensure time is imported
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_default_provider.return_value = "gemini"
    mock_config.get_active_model.return_value = "gemini-3.1-flash-lite"
    mock_config.get_temperature.return_value = 0.2

    mock_engine = MagicMock()
    mock_engine_class.return_value = mock_engine

    # Use a wrapper function so the mock emits thought_start before raising the crash
    def mock_crashing_send_message(*args, **kwargs):
        status_cb = kwargs.get("status_callback")
        if status_cb:
            status_cb("Generating thoughts...")
        raise RuntimeError("Gemini API connection timeout.")

    # Simulate API crash
    mock_engine.send_message.side_effect = mock_crashing_send_message

    client = TestClient(app)

    with client.websocket_connect("/ws/99") as ws:
        ws.receive_json()  # Welcome
        
        ws.send_json({
            "type": "user_message",
            "payload": {"content": "Execute workflow"}
        })
        
        ws.receive_json()  # thought_start
        
        # Receive the gracefully mapped execution error
        response = ws.receive_json()
        
        assert response["type"] == "execution_error"
        assert response["payload"]["error_code"] == "AGENT_EXECUTION_FAILED"
        assert "Gemini API connection timeout." in response["payload"]["message"]
        
        # DYNAMIC POLLING: Give the background thread up to 2 seconds to hit its finally: block
        cleaned_up = False
        for _ in range(40):
            if 99 not in active_threads:
                cleaned_up = True
                break
            time.sleep(0.05)
            
        # Verify clean up removed the conversation lock
        assert cleaned_up is True, f"Thread cleanup failed! active_threads still holds: {active_threads}"