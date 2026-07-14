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
# This ensures Chat 1 and Chat 2 run completely independent tasks.
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
        """
        Sends a message to all connected tabs/windows.
        The React frontend will use the 'conversation_id' in the message
        to balance and route the data to the correct chat UI.
        """
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


# =====================================================================
# 1. THE MAIN MULTIPLEXER (TRAFFIC COP)
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
                await websocket.send_json(
                    {"type": "error", "payload": {"message": "Malformed JSON"}}
                )
                continue

            msg_type = message.get("type")
            payload = message.get("payload", {})
            conv_id = payload.get("conversation_id")

            # Route to dedicated helper functions
            if msg_type == "init_session":
                await _handle_init_session(websocket)

            elif msg_type == "load_history":
                await _handle_load_history(websocket, conv_id, payload)

            elif msg_type == "search_threads":
                await _handle_search_threads(websocket, payload)

            elif msg_type == "user_message":
                await _handle_user_message(websocket, conv_id, payload)

            elif msg_type == "approval_response":
                _handle_approval_response(conv_id, payload)

            elif msg_type == "cancel_execution":
                _handle_cancel_execution(conv_id)

            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "payload": {"message": f"Unknown event type: {msg_type}"},
                    }
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        _cleanup_disconnected_client()


# =====================================================================
# 2. ISOLATED ROUTE HANDLERS
# =====================================================================


async def _handle_init_session(websocket: WebSocket):
    """Handles the initial bootup payload for the UI."""
    recent_convs = get_conversations_paginated(limit=20, offset=0)
    await websocket.send_json(
        {
            "type": "session_state",
            "payload": {
                "active_provider": config_manager.get_default_provider(),
                "active_model": config_manager.get_active_model(
                    config_manager.get_default_provider()
                ),
                "temperature": config_manager.get_temperature(),
                "recent_threads": recent_convs,
            },
        }
    )


async def _handle_load_history(websocket: WebSocket, conv_id: int, payload: dict):
    """Handles infinite scroll pagination for messages."""
    if not conv_id:
        return
    before_id = payload.get("before_id")
    msgs = get_messages_paginated(conv_id, before_id=before_id, limit=20)
    await websocket.send_json(
        {
            "type": "history_loaded",
            "conversation_id": conv_id,
            "payload": {"messages": msgs},
        }
    )


async def _handle_search_threads(websocket: WebSocket, payload: dict):
    """Handles live sidebar search filtering."""
    search_term = payload.get("query", "")
    results = search_conversations(search_term, limit=20)
    await websocket.send_json(
        {"type": "search_results", "payload": {"results": results}}
    )


async def _handle_user_message(websocket: WebSocket, conv_id: int, payload: dict):
    """Handles concurrency checks, DB creation, and spawning the ReAct engine thread."""
    user_text = payload.get("content")
    if not user_text:
        return

    # Concurrency Cap Check
    max_chats = config_manager.get_max_concurrent_chats()
    if len(active_threads) >= max_chats and conv_id not in active_threads:
        await websocket.send_json(
            {
                "type": "execution_error",
                "conversation_id": conv_id,
                "payload": {
                    "error_code": "CONCURRENCY_LIMIT_REACHED",
                    "message": f"You can only run {max_chats} agents at once. Please wait for one to finish.",
                },
            }
        )
        return

    # If it's a brand new chat, create it in the DB first
    if not conv_id:
        new_conv = create_conversation(title=user_text[:40] + "...")
        conv_id = new_conv["id"]
        await websocket.send_json(
            {
                "type": "conversation_created",
                "conversation_id": conv_id,
                "payload": new_conv,
            }
        )

    # Prevent double-execution on the same thread
    if conv_id in active_threads:
        await websocket.send_json(
            {
                "type": "execution_error",
                "conversation_id": conv_id,
                "payload": {
                    "error_code": "CONCURRENT_RUN_BLOCKED",
                    "message": "Agent is already running in this thread.",
                },
            }
        )
        return

    # Spawn the background worker for this specific conversation
    loop = asyncio.get_running_loop()
    t = threading.Thread(
        target=run_agent_workflow, args=(conv_id, user_text, loop), daemon=True
    )
    active_threads[conv_id] = t
    t.start()


def _handle_approval_response(conv_id: int, payload: dict):
    """Unfreezes the engine thread with the user's decision."""
    if conv_id:
        approved = payload.get("approved", False)
        resolve_decision(conv_id, approved=approved)


def _handle_cancel_execution(conv_id: int):
    """Forcefully denies an approval to cancel execution."""
    if conv_id:
        resolve_decision(conv_id, approved=False)


def _cleanup_disconnected_client():
    """Releases any waiting approvals to prevent zombie threads on disconnect."""
    for c_id in list(active_threads.keys()):
        resolve_decision(c_id, approved=False)


# =====================================================================
# 3. BACKGROUND WORKER & CALLBACKS
# =====================================================================


def run_agent_workflow(
    conversation_id: int, user_text: str, loop: asyncio.AbstractEventLoop
):
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

        # Thread-safe approval interceptor
        def websocket_approval_callback(
            tool_name: str, tool_args: dict, c_id: int
        ) -> bool:
            approval_msg = {
                "type": "approval_required",
                "conversation_id": c_id,
                "payload": {"tool_name": tool_name, "arguments": tool_args},
            }
            asyncio.run_coroutine_threadsafe(manager.broadcast(approval_msg), loop)
            return wait_for_decision(c_id, timeout=300)

        # Partial out callbacks
        status_cb = partial(websocket_status_callback, loop, conversation_id)
        stream_cb = partial(
            websocket_stream_callback, loop, conversation_id
        )  # <-- ADD THIS

        # Start execution turn
        final_response = engine.send_message(
            conversation_id=conversation_id,
            user_text=user_text,
            source="web",
            send_message_callback=stream_cb,
            status_callback=status_cb,
            approval_callback=websocket_approval_callback,
        )

        # Close out the timeline
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(
                {
                    "type": "execution_completed",
                    "conversation_id": conversation_id,
                    "payload": {"status": "success"},
                }
            ),
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
        # Notify UI that this thread is free again
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(
                {
                    "type": "thread_freed",
                    "conversation_id": conversation_id,
                    "payload": {},
                }
            ),
            loop,
        )


def websocket_stream_callback(
    loop: asyncio.AbstractEventLoop, conversation_id: int, text_chunk: str
):
    """Streams text chunks to the frontend via WebSockets."""
    if text_chunk:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(
                {
                    "type": "message_chunk",
                    "conversation_id": conversation_id,
                    "payload": {"chunk": text_chunk},
                }
            ),
            loop,
        )


def websocket_status_callback(
    loop: asyncio.AbstractEventLoop, conversation_id: int, status_text: str
):
    """Parses flat string updates into structured client events."""
    event = {"conversation_id": conversation_id}

    if "Generating thoughts..." in status_text:
        event["type"] = "thought_start"
        event["payload"] = {"timestamp": loop.time()}
    elif "Executing tool" in status_text:
        tool_name = "unknown"
        tool_args = {}
        try:
            parts = status_text.split("Executing tool '")[1].split(
                "' with arguments:\n"
            )
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
