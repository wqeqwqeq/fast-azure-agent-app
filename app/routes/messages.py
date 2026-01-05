"""Message API routes with SSE streaming for workflow execution."""

import logging
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..dependencies import CurrentUserDep, HistoryManagerDep
from ..opsagent.middleware.observability import set_current_stream
from ..opsagent.schemas.common import MessageData, WorkflowInput
from ..opsagent.workflows.dynamic_workflow import create_dynamic_workflow
from ..opsagent.workflows.triage_workflow import create_triage_workflow
from ..schemas import MessageSchema, SendMessageRequest, SendMessageResponse
from ..utils.event_stream import AsyncEventStream

logger = logging.getLogger(__name__)

router = APIRouter()

# Store active EventStream instances keyed by conversation_id
_active_streams: Dict[str, AsyncEventStream] = {}


def title_from_first_user_message(msg: str) -> str:
    """Derive a short, single-line chat title from the user's first message.

    Args:
        msg: The user's message

    Returns:
        A short title (max 29 characters)
    """
    trimmed = (msg or "New chat").strip().replace("\n", " ")
    return (trimmed[:28] + "…") if len(trimmed) > 29 else (trimmed if trimmed else "New chat")


async def call_llm(model: str, messages: list[dict]) -> str:
    """Execute the workflow with conversation history.

    Uses dynamic workflow if DYNAMIC_PLAN=true, otherwise uses triage workflow.
    Creates a fresh workflow instance per request for thread-safety.

    Args:
        model: Model identifier (currently unused, workflow uses default)
        messages: List of message dicts with "role" and "content" fields

    Returns:
        Assistant response text
    """
    settings = get_settings()

    try:
        # Create fresh workflow for this request
        if settings.dynamic_plan:
            # Use dynamic workflow with review loop
            workflow = create_dynamic_workflow()
        else:
            # Use standard triage workflow
            workflow = create_triage_workflow()

        # Convert messages to workflow input format
        message_data = [
            MessageData(role=msg["role"], text=msg["content"])
            for msg in messages
        ]
        input_data = WorkflowInput(messages=message_data)

        # Run async workflow
        result = await workflow.run(input_data)

        # Extract output
        outputs = result.get_outputs()
        if outputs:
            return outputs[0]
        return "No response from workflow"

    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        return f"Error: Unable to process request. {str(e)}"


@router.get("/conversations/{conversation_id}/thinking")
async def thinking_stream(conversation_id: str):
    """SSE endpoint for streaming thinking events during workflow execution.

    This endpoint should be connected BEFORE sending a message.
    Events are pushed by middleware during workflow.run() execution.

    Args:
        conversation_id: Conversation ID

    Returns:
        StreamingResponse with Server-Sent Events
    """

    async def event_generator():
        # Create and register stream for this conversation
        stream = AsyncEventStream()
        _active_streams[conversation_id] = stream
        await stream.start()

        # Send initial comment to establish connection and flush buffers
        # This helps with Azure App Service proxy buffering
        yield ": connected\n\n"

        try:
            # Yield events as they arrive (async blocking)
            async for event in stream.iter_events():
                yield f"data: {event}\n\n"
        finally:
            # Cleanup when stream ends or client disconnects
            if conversation_id in _active_streams:
                del _active_streams[conversation_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",  # Nginx
            "X-Content-Type-Options": "nosniff",
            "Content-Type": "text/event-stream; charset=utf-8",
            # Azure App Service specific - disable ARR buffering
            "X-ARR-Disable-Session-Affinity": "true",
            "Transfer-Encoding": "chunked",
        },
    )


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    history: HistoryManagerDep,
    current_user: CurrentUserDep,
) -> SendMessageResponse:
    """Send a message to a conversation and get LLM response.

    Args:
        conversation_id: Conversation ID
        body: SendMessageRequest with user message

    Returns:
        SendMessageResponse with user message, assistant response, and title

    Raises:
        HTTPException: 404 if conversation not found
    """
    user_id = current_user.user_id
    user_message = body.message.strip()

    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Get conversation
    convo = await history.get_conversation(conversation_id, user_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Append user message
    now = datetime.now(timezone.utc).isoformat()
    convo["messages"].append({
        "role": "user",
        "content": user_message,
        "time": now,
    })

    # Auto-generate title from first message
    if convo["title"] == "New chat":
        convo["title"] = title_from_first_user_message(user_message)

    # Get the thinking stream for this conversation (if frontend connected)
    stream = _active_streams.get(conversation_id)

    # Set as current stream for middleware to use
    set_current_stream(stream)

    try:
        # Call workflow (middleware will emit events to stream)
        # Build OpenAI-style message list for workflow
        llm_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in convo["messages"]
        ]
        reply = await call_llm(convo["model"], llm_messages)
    finally:
        # Stop the stream and clear current stream
        if stream:
            await stream.stop()
        set_current_stream(None)

    # Append assistant message
    assistant_time = datetime.now(timezone.utc).isoformat()
    convo["messages"].append({
        "role": "assistant",
        "content": reply,
        "time": assistant_time,
    })

    # Update last_modified (moves chat to top of list)
    convo["last_modified"] = assistant_time

    # Save to storage (write-through: postgres first, then redis)
    await history.save_conversation(conversation_id, user_id, convo)

    return SendMessageResponse(
        user_message=MessageSchema(
            role="user",
            content=user_message,
            time=now,
        ),
        assistant_message=MessageSchema(
            role="assistant",
            content=reply,
            time=assistant_time,
        ),
        title=convo["title"],
    )
