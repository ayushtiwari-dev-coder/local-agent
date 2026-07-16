# interfaces/websocket.py
import os
import ast
import json
import asyncio
import threading
from typing import Dict, List
from functools import partial
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

import utils.config_manager as config_manager
import config_configure.in_chat_config as in_chat_config
import config_configure.out_chat_config as out_chat_config
from engine.agent_engine import AgentEngine
from managers.approval_manager import wait_for_decision, resolve_decision
from queries.conversation_queries import (
    get_conversations_paginated,
    search_conversations,
    create_conversation,
)
from queries.message_queries import get_messages_paginated

router = APIRouter()

# Thread-safe mapping: conversation_id -> threading.Thread
active_threads: Dict[int, threading.Thread] = {}

class ConnectionManager:
    """Manages the Global WebSocket connection for the local user."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Sends a message to all connected tabs/windows."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# =====================================================================
# 1. SUPPORTING CALLBACKS & BACKGROUND WORKERS
# =====================================================================

def _cleanup_disconnected_client():
    """Releases any waiting approvals to prevent zombie threads on disconnect."""
    for c_id in list(active_threads.keys()):
        resolve_decision(c_id, approved=False)

def websocket_stream_callback(loop: asyncio.AbstractEventLoop, conversation_id: int, text_chunk: str):
    """Streams text chunks to the frontend via WebSockets."""
    if text_chunk:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type": "message_chunk",
                "conversation_id": conversation_id,
                "payload": {"chunk": text_chunk},
            }),
            loop,
        )

def websocket_status_callback(loop: asyncio.AbstractEventLoop, conversation_id: int, status_text: str):
    """Parses flat string updates into structured client events."""
    event = {"conversation_id": conversation_id}
    
    if "Generating thoughts..." in status_text:
        event["type"] = "thought_start"
        event["payload"] = {"timestamp": loop.time()}
        
    elif "Executing tool" in status_text:
        tool_name = "unknown"
        tool_args = {}
        try:
            parts = status_text.split("Executing tool '")[1].split("' with arguments:\n")
            tool_name = parts[0]
            tool_args = ast.literal_eval(parts[1].strip())
        except Exception:
            pass
        event["type"] = "tool_start"
        event["payload"] = {
            "tool_name": tool_name,
            "arguments": tool_args,
            "timestamp": loop.time(),
        }
        
    elif "returned status" in status_text:
        tool_name = "unknown"
        status = "unknown"
        try:
            parts = status_text.split("Tool '")[1].split("' returned status: '")
            tool_name = parts[0]
            status = parts[1].replace("'", "").strip()
        except Exception:
            pass
        event["type"] = "tool_end"
        event["payload"] = {
            "tool_name": tool_name,
            "status": status,
            "timestamp": loop.time(),
        }
        
    else:
        event["type"] = "status_update"
        event["payload"] = {"message": status_text}
        
    asyncio.run_coroutine_threadsafe(manager.broadcast(event), loop)

def run_agent_workflow(conversation_id: int, user_text: str, loop: asyncio.AbstractEventLoop):
    """Target worker executed inside an OS thread."""
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
        
        def websocket_approval_callback(tool_name: str, tool_args: dict, c_id: int) -> bool:
            approval_msg = {
                "type": "approval_required",
                "conversation_id": c_id,
                "payload": {"tool_name": tool_name, "arguments": tool_args},
            }
            asyncio.run_coroutine_threadsafe(manager.broadcast(approval_msg), loop)
            return wait_for_decision(c_id, timeout=300)

        status_cb = partial(websocket_status_callback, loop, conversation_id)
        stream_cb = partial(websocket_stream_callback, loop, conversation_id)

        final_response = engine.send_message(
            conversation_id=conversation_id,
            user_text=user_text,
            source="web",
            send_message_callback=stream_cb,
            status_callback=status_cb,
            approval_callback=websocket_approval_callback,
        )

        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type": "execution_completed",
                "conversation_id": conversation_id,
                "payload": {"status": "success"},
            }),
            loop,
        )
        
    except Exception as e:
        error_msg = {
            "type": "execution_error",
            "conversation_id": conversation_id,
            "payload": {
                "error_code": "AGENT_EXECUTION_FAILED",
                "message": str(e),
                "fatal": True,
            },
        }
        asyncio.run_coroutine_threadsafe(manager.broadcast(error_msg), loop)
        
    finally:
        active_threads.pop(conversation_id, None)
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type": "thread_freed",
                "conversation_id": conversation_id,
                "payload": {},
            }),
            loop,
        )

# =====================================================================
# 2. STANDARDIZED ROUTE HANDLERS
# =====================================================================

async def _handle_init_session(websocket: WebSocket, conv_id: int, payload: dict):
    recent_convs = get_conversations_paginated(limit=20, offset=0)
    await websocket.send_json({
        "type": "session_state",
        "payload": {
            "active_provider": config_manager.get_default_provider(),
            "active_model": config_manager.get_active_model(config_manager.get_default_provider()),
            "temperature": config_manager.get_temperature(),
            "recent_threads": recent_convs,
        }
    })

async def _handle_load_history(websocket: WebSocket, conv_id: int, payload: dict):
    if not conv_id:
        return
    before_id = payload.get("before_id")
    msgs = get_messages_paginated(conv_id, before_id=before_id, limit=20)
    await websocket.send_json({
        "type": "history_loaded",
        "conversation_id": conv_id,
        "payload": {"messages": msgs},
    })

async def _handle_search_threads(websocket: WebSocket, conv_id: int, payload: dict):
    search_term = payload.get("query", "")
    results = search_conversations(search_term, limit=20)
    await websocket.send_json({
        "type": "search_results",
        "payload": {"results": results}
    })

async def _handle_user_message(websocket: WebSocket, conv_id: int, payload: dict):
    user_text = payload.get("content")
    if not user_text:
        return

    max_chats = config_manager.get_max_concurrent_chats()
    if len(active_threads) >= max_chats and conv_id not in active_threads:
        await websocket.send_json({
            "type": "execution_error",
            "conversation_id": conv_id,
            "payload": {
                "error_code": "CONCURRENCY_LIMIT_REACHED",
                "message": f"You can only run {max_chats} agents at once. Please wait for one to finish.",
            },
        })
        return

    if not conv_id:
        new_conv = create_conversation(title=user_text[:40] + "...")
        conv_id = new_conv["id"]
        await websocket.send_json({
            "type": "conversation_created",
            "conversation_id": conv_id,
            "payload": new_conv,
        })

    if conv_id in active_threads:
        await websocket.send_json({
            "type": "execution_error",
            "conversation_id": conv_id,
            "payload": {
                "error_code": "CONCURRENT_RUN_BLOCKED",
                "message": "Agent is already running in this thread.",
            },
        })
        return

    loop = asyncio.get_running_loop()
    t = threading.Thread(
        target=run_agent_workflow, args=(conv_id, user_text, loop), daemon=True
    )
    active_threads[conv_id] = t
    t.start()

async def _handle_approval_response(websocket: WebSocket, conv_id: int, payload: dict):
    if conv_id:
        approved = payload.get("approved", False)
        resolve_decision(conv_id, approved=approved)

async def _handle_cancel_execution(websocket: WebSocket, conv_id: int, payload: dict):
    if conv_id:
        resolve_decision(conv_id, approved=False)

async def _handle_get_settings(websocket: WebSocket, conv_id: int, payload: dict):
    config = config_manager.load_config()
    providers_status = out_chat_config.get_providers_status()
    await websocket.send_json({
        "type": "settings_data",
        "payload": {
            "config": config,
            "providers_status": providers_status.get("data", {}),
        }
    })

async def _handle_update_setting(websocket: WebSocket, conv_id: int, payload: dict):
    setting_type = payload.get("setting_type")
    data = payload.get("data", {})
    
    if setting_type not in SETTING_DISPATCHER:
        res = {"status": "error", "message": f"Unknown setting type: {setting_type}"}
    else:
        try:
            res = SETTING_DISPATCHER[setting_type](data)
        except (ValueError, TypeError) as e:
            res = {"status": "error", "message": f"Invalid data format: {e}"}
        except Exception as e:
            res = {"status": "error", "message": str(e)}

    await websocket.send_json({
        "type": "setting_updated",
        "payload": {
            "setting_type": setting_type,
            "result": res,
        }
    })
    
    if res.get("status") == "success":
        await _handle_get_settings(websocket, conv_id, payload)

# =====================================================================
# 3. O(1) DISPATCH TABLES (Defined below handlers to avoid NameErrors)
# =====================================================================

SETTING_DISPATCHER = {
    "api_key": lambda d: out_chat_config.validate_and_set_api_key(
        str(d.get("provider", "")), str(d.get("key", "")), bool(d.get("force_save", False))
    ),
    "active_model": lambda d: in_chat_config.switch_active_model(
        str(d.get("provider", "")), str(d.get("model", ""))
    ),
    "temperature": lambda d: in_chat_config.update_temperature(
        float(d.get("value", 0.2))
    ),
    "thinking_level": lambda d: in_chat_config.update_thinking_level(
        str(d.get("value", "high"))
    ),
    "system_instruction": lambda d: out_chat_config.update_system_instruction(
        d.get("value")
    ),
    "max_turns": lambda d: out_chat_config.update_max_turns(
        int(d.get("value", 15))
    ),
    "loop_guard": lambda d: out_chat_config.update_loop_guard(
        d.get("max_failed"), d.get("max_success")
    ),
}

WS_EVENT_ROUTER = {
    "init_session": _handle_init_session,
    "load_history": _handle_load_history,
    "search_threads": _handle_search_threads,
    "user_message": _handle_user_message,
    "approval_response": _handle_approval_response,
    "cancel_execution": _handle_cancel_execution,
    "get_settings": _handle_get_settings,
    "update_setting": _handle_update_setting,
}

# =====================================================================
# 4. THE WEB PORT MULTIPLEXER (MAIN TRAFFIC COP)
# =====================================================================

@router.websocket("/ws/main")
async def global_websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    """The Single Global Multiplexer Endpoint."""
    
    # Handshake Security Check
    expected_token = config_manager.get_provider_api_key("gemini")
    if token and expected_token and token != expected_token:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": "Malformed JSON"},
                })
                continue

            msg_type = message.get("type")
            payload = message.get("payload", {})
            conv_id = payload.get("conversation_id")

            # Execute unified signature dynamic handlers
            handler = WS_EVENT_ROUTER.get(msg_type)
            if handler:
                await handler(websocket, conv_id, payload)
            else:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": f"Unknown event type: {msg_type}"},
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        _cleanup_disconnected_client()