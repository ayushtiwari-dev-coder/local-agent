# interfaces/websocket.py
import os
import ast
import json
import asyncio
import threading
from typing import Dict
from functools import partial
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

import utils.config_manager as config_manager
from engine.agent_engine import AgentEngine
from managers.approval_manager import wait_for_decision, resolve_decision

router = APIRouter()

# Thread-safe mapping to ensure we track and prevent concurrent execution per conversation
active_threads: Dict[int, threading.Thread] = {}

class ConnectionManager:
    """Manages active single-user WebSocket channels."""
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, conversation_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[conversation_id] = websocket

    def disconnect(self, conversation_id: int):
        if conversation_id in self.active_connections:
            del self.active_connections[conversation_id]

    async def send_personal_message(self, message: dict, conversation_id: int):
        websocket = self.active_connections.get(conversation_id)
        if websocket:
            await websocket.send_json(message)

manager = ConnectionManager()



@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: int, token: str = Query(None)):
    """Central gateway endpoint for WebSocket lifecycle routing."""
    # Simple validation using stored model credentials
    expected_token = config_manager.get_provider_api_key("gemini")
    if token and expected_token and token != expected_token:
        await websocket.close(code=4001)
        return

    await manager.connect(conversation_id, websocket)

    # Dispatch welcome configuration details
    welcome_msg = {
        "type": "connection_established",
        "payload": {
            "session_id": f"session_{conversation_id}",
            "active_provider": config_manager.get_default_provider(),
            "active_model": config_manager.get_active_model(config_manager.get_default_provider()),
            "temperature": config_manager.get_temperature()
        }
    }
    await websocket.send_json(welcome_msg)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await handle_client_message(conversation_id, message, websocket)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "execution_error",
                    "payload": {
                        "error_code": "MALFORMED_JSON",
                        "message": "Malformed client payload. Expected valid JSON."
                    }
                })
    except WebSocketDisconnect:
        manager.disconnect(conversation_id)
        # Prevent thread hanging by releasing any waiting approvals negatively
        resolve_decision(conversation_id, approved=False)


async def handle_client_message(conversation_id: int, message: dict, websocket: WebSocket):
    """Parses and acts on incoming payloads from the React browser."""
    msg_type = message.get("type")
    payload = message.get("payload", {})

    if msg_type == "user_message":
        user_text = payload.get("content")
        if not user_text:
            return

        if conversation_id in active_threads:
            await websocket.send_json({
                "type": "execution_error",
                "payload": {
                    "error_code": "CONCURRENT_RUN_BLOCKED",
                    "message": "An active workflow is already running in this session."
                }
            })
            return

        # Fetch active running loop to capture asynchronous context
        loop = asyncio.get_running_loop()
        t = threading.Thread(
            target=run_agent_workflow,
            args=(conversation_id, user_text, loop),
            daemon=True
        )
        active_threads[conversation_id] = t
        t.start()

    elif msg_type == "approval_response":
        approved = payload.get("approved", False)
        resolve_decision(conversation_id, approved=approved)

    elif msg_type == "cancel_execution":
        resolve_decision(conversation_id, approved=False)
        await websocket.send_json({
            "type": "execution_cancelled",
            "payload": {
                "reason": "user_aborted"
            }
        })


def run_agent_workflow(conversation_id: int, user_text: str, loop: asyncio.AbstractEventLoop):
    """
    Target worker executed inside an OS thread.
    Performs the synchronous heavy-lifting of the ReAct engine run.
    """
    try:
        provider_choice = config_manager.get_default_provider()
        model_choice = config_manager.get_active_model(provider_choice)
        resolved_key = config_manager.get_provider_api_key(provider_choice)

        engine = AgentEngine(
            provider_name=provider_choice,
            model_name=model_choice,
            api_key=resolved_key,
            autonomous=False,
        )

        # Thread-safe approval interceptor
        def websocket_approval_callback(tool_name: str, tool_args: dict, c_id: int) -> bool:
            approval_msg = {
                "type": "approval_required",
                "payload": {
                    "tool_name": tool_name,
                    "arguments": tool_args
                }
            }
            asyncio.run_coroutine_threadsafe(
                manager.send_personal_message(approval_msg, c_id),
                loop
            )
            # Freeze background thread until approval manager receives a web-UI resolution
            return wait_for_decision(c_id, timeout=300)

        # Partial out status callback with the thread event loop context
        status_cb = partial(websocket_status_callback, loop, conversation_id)

        # Start execution turn
        final_response = engine.send_message(
            conversation_id=conversation_id,
            user_text=user_text,
            source="web",
            status_callback=status_cb,
            approval_callback=websocket_approval_callback
        )

        # Send final text chunk message
        asyncio.run_coroutine_threadsafe(
            manager.send_personal_message({
                "type": "message_chunk",
                "payload": {"chunk": final_response}
            }, conversation_id),
            loop
        )

        # Close out the timeline
        complete_msg = {
            "type": "execution_completed",
            "payload": {
                "status": "success",
                "usage": {
                    "model_name": model_choice,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            }
        }
        asyncio.run_coroutine_threadsafe(
            manager.send_personal_message(complete_msg, conversation_id),
            loop
        )

    except Exception as e:
        error_msg = {
            "type": "execution_error",
            "payload": {
                "error_code": "AGENT_EXECUTION_FAILED",
                "message": str(e),
                "fatal": True
            }
        }
        asyncio.run_coroutine_threadsafe(
            manager.send_personal_message(error_msg, conversation_id),
            loop
        )
    finally:
        active_threads.pop(conversation_id, None)


def websocket_status_callback(loop: asyncio.AbstractEventLoop, conversation_id: int, status_text: str):
    """
    Synchronous callback executed by the background AgentEngine thread.
    Parses flat string updates into structured client events and marshals them
    across the thread boundary to FastAPI's async event loop.
    """
    event = {}
    
    if "Generating thoughts..." in status_text:
        event = {
            "type": "thought_start",
            "payload": {"timestamp": loop.time()}
        }
    elif "Executing tool" in status_text:
        tool_name = "unknown"
        tool_args = {}
        try:
            # Parse: "Executing tool 'read_files' with arguments:\n{'paths': ['test.txt']}"
            parts = status_text.split("Executing tool '")[1].split("' with arguments:\n")
            tool_name = parts[0]
            # Safely parse the Python dictionary string representation without using eval()
            tool_args = ast.literal_eval(parts[1].strip())
        except Exception:
            pass
            
        event = {
            "type": "tool_start",
            "payload": {
                "tool_name": tool_name,
                "arguments": tool_args,
                "timestamp": loop.time()
            }
        }
    elif "returned status" in status_text:
        tool_name = "unknown"
        status = "unknown"
        try:
            # Parse: "Tool 'read_files' returned status: 'success'"
            parts = status_text.split("Tool '")[1].split("' returned status: '")
            tool_name = parts[0]
            status = parts[1].replace("'", "").strip()
        except Exception:
            pass
            
        event = {
            "type": "tool_end",
            "payload": {
                "tool_name": tool_name,
                "status": status,
                "timestamp": loop.time()
            }
        }
    else:
        # Fallback for miscellaneous updates
        event = {
            "type": "status_update",
            "payload": {"message": status_text}
        }

    # Execute thread-safe async scheduling
    asyncio.run_coroutine_threadsafe(
        manager.send_personal_message(event, conversation_id),
        loop
    )
