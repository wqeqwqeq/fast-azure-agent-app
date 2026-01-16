"""Message API routes with unified SSE streaming for workflow execution."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent_framework._workflows._events import AgentRunUpdateEvent, WorkflowOutputEvent

from ..config import get_settings
from ..dependencies import CurrentUserDep, HistoryManagerDep
from ..core.events import set_current_message_seq, set_current_queue
from ..opsagent.schemas.common import MessageData, WorkflowInput
from ..opsagent.workflows.dynamic_workflow import create_dynamic_workflow
from ..opsagent.workflows.triage_workflow import create_triage_workflow
from ..schemas import SendMessageRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def title_from_first_user_message(msg: str) -> str:
    """Derive a short, single-line chat title from the user's first message.

    Args:
        msg: The user's message

    Returns:
        A short title (max 29 characters)
    """
    trimmed = (msg or "New chat").strip().replace("\n", " ")
    return (trimmed[:28] + "…") if len(trimmed) > 29 else (trimmed if trimmed else "New chat")


def format_sse_event(event_type: str, data: dict) -> str:
    """Format data as an SSE event string.

    Args:
        event_type: The SSE event type (e.g., 'thinking', 'message', 'done')
        data: Dictionary to JSON serialize as event data

    Returns:
        Formatted SSE event string
    """
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    request: Request,
    history: HistoryManagerDep,
    current_user: CurrentUserDep,
):
    """Send a message and stream thinking events + final response via SSE.

    This unified endpoint streams middleware events (function_start/end, agent events)
    in real-time and returns the final assistant response as part of the same stream.

    Events emitted:
    - message (user): Confirms user message saved
    - thinking (function_start/end, agent_invoked/finished): From middleware
    - message (assistant): Final response from workflow
    - done: Stream complete

    Args:
        conversation_id: Conversation ID
        body: SendMessageRequest with user message

    Returns:
        StreamingResponse with SSE events

    Raises:
        HTTPException: 404 if conversation not found
    """
    user_id = current_user.user_id
    user_message = body.message  # Already stripped by Pydantic validator

    # Get conversation
    convo = await history.get_conversation(conversation_id, user_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Calculate message sequence number (user message index)
    user_message_seq = len(convo["messages"])

    # Resolve workflow_model: request > conversation.model > fallback
    workflow_model = body.workflow_model or convo.get("model") or get_settings().default_model

    # Get agent level LLM overwrite from request (already validated by Pydantic)
    agent_level_llm_overwrite = body.agent_level_llm_overwrite

    # Append user message (model selection stored at conversation level, not per-message)
    now = datetime.now(timezone.utc).isoformat()
    convo["messages"].append({
        "role": "user",
        "content": user_message,
        "time": now,
    })

    # Auto-generate title from first message
    if convo["title"] == "New chat":
        convo["title"] = title_from_first_user_message(user_message)

    async def event_generator():
        """Generate SSE events from workflow execution."""
        # Create event queue for middleware to emit to
        event_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        final_output: Optional[str] = None
        workflow_error: Optional[str] = None

        async def run_workflow():
            """Run the workflow and emit events to the queue."""
            nonlocal final_output, workflow_error

            try:
                # Set up context for middleware
                set_current_queue(event_queue)
                set_current_message_seq(user_message_seq)

                # Get model registry from app state
                registry = request.app.state.model_registry

                # Create fresh workflow for this request with resolved model config
                # Use react_mode from request body (default: False = triage workflow)
                if body.react_mode:
                    workflow = create_dynamic_workflow(registry, workflow_model, agent_level_llm_overwrite)
                else:
                    workflow = create_triage_workflow(registry, workflow_model, agent_level_llm_overwrite)

                # Auto-detect streaming executors from workflow (those with output_response=True)
                streaming_executor_ids = {
                    executor_id
                    for executor_id, executor in workflow.executors.items()
                    if getattr(executor, 'output_response', False)
                }

                # Convert messages to workflow input format
                message_data = [
                    MessageData(role=msg["role"], text=msg["content"])
                    for msg in convo["messages"]
                ]
                input_data = WorkflowInput(messages=message_data)

                # Run workflow with streaming
                # Middleware events (function_start/end, agent events) are emitted
                # directly to the queue via observability middleware.
                # AgentRunUpdateEvent contains streaming text from summary agent.
                # WorkflowOutputEvent contains the final complete response.
                async for event in workflow.run_stream(input_data):
                    if isinstance(event, AgentRunUpdateEvent):
                        # Stream text updates only from executors with output_response=True
                        if event.executor_id in streaming_executor_ids:
                            update_text = event.data.text if event.data else ""
                            if update_text:
                                await event_queue.put(format_sse_event("stream", {
                                    "type": "stream",
                                    "executor_id": event.executor_id,
                                    "text": update_text,
                                    "seq": user_message_seq,
                                }))
                                # Small delay for visible streaming effect (non-blocking)
                                await asyncio.sleep(0.005)
                    elif isinstance(event, WorkflowOutputEvent):
                        # Handle both string output and AgentRunResponse object
                        if hasattr(event.data, 'text'):
                            final_output = event.data.text
                        else:
                            final_output = event.data

            except Exception as e:
                logger.error(f"Workflow execution failed: {e}")
                workflow_error = str(e)
            finally:
                # Clear context
                set_current_queue(None)
                set_current_message_seq(None)
                # Signal completion
                await event_queue.put(None)

        # Start workflow in background task
        workflow_task = asyncio.create_task(run_workflow())

        # Emit user message saved event
        yield format_sse_event("message", {
            "type": "user",
            "content": user_message,
            "seq": user_message_seq,
            "time": now,
        })

        # Yield events from queue as they arrive
        # These are middleware events (function_start/end, agent_invoked/finished)
        # AND stream events from summary agent
        try:
            while True:
                event = await event_queue.get()
                if event is None:
                    break
                yield event
        except asyncio.CancelledError:
            workflow_task.cancel()
            raise

        # Wait for workflow to complete
        await workflow_task

        # Handle result
        if workflow_error:
            reply = f"Error: Unable to process request. {workflow_error}"
        elif final_output:
            reply = final_output
        else:
            reply = "No response from workflow"

        # Append assistant message
        assistant_time = datetime.now(timezone.utc).isoformat()
        convo["messages"].append({
            "role": "assistant",
            "content": reply,
            "time": assistant_time,
        })

        # Update last_modified
        convo["last_modified"] = assistant_time

        # Update conversation with user's model selection (remembers for next time)
        convo["model"] = workflow_model
        if agent_level_llm_overwrite:
            convo["agent_level_llm_overwrite"] = agent_level_llm_overwrite.model_dump(exclude_none=True)

        # Save to storage
        await history.save_conversation(conversation_id, user_id, convo)

        # Emit assistant message
        assistant_seq = user_message_seq + 1
        yield format_sse_event("message", {
            "type": "assistant",
            "content": reply,
            "seq": assistant_seq,
            "time": assistant_time,
            "title": convo["title"],
        })

        # Signal completion
        yield format_sse_event("done", {})

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
