"""Call tracking API routes."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from ..dependencies import CurrentUserDep, HistoryManagerDep

router = APIRouter()


@router.get("/conversations/{conversation_id}/calls")
async def get_calls(
    conversation_id: str,
    request: Request,
    history: HistoryManagerDep,
    current_user: CurrentUserDep,
):
    """Get all agent and function calls for a conversation.

    Returns call records with token usage and timing metrics,
    along with a summary of totals.

    Args:
        conversation_id: Conversation ID

    Returns:
        Dict with calls list and summary statistics
    """
    user_id = current_user.user_id

    # Verify conversation exists and belongs to user
    convo = await history.get_conversation(conversation_id, user_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get calls from backend
    call_backend = request.app.state.call_backend
    calls = await call_backend.get_calls_by_conversation(conversation_id)

    # Convert to serializable format (handle datetime serialization)
    calls_data = []
    for c in calls:
        call_dict = asdict(c)
        # Convert datetime to ISO string for JSON serialization
        if call_dict.get("created_at"):
            call_dict["created_at"] = call_dict["created_at"].isoformat()
        calls_data.append(call_dict)

    # Calculate summary statistics
    total_input_tokens = sum(c.input_tokens or 0 for c in calls)
    total_output_tokens = sum(c.output_tokens or 0 for c in calls)
    total_tokens = sum(c.total_tokens or 0 for c in calls)
    total_execution_time_ms = sum(c.execution_time_ms or 0 for c in calls)

    # Count by type
    agent_calls = [c for c in calls if c.agent_name]
    function_calls = [c for c in calls if c.function_name]

    return {
        "conversation_id": conversation_id,
        "calls": calls_data,
        "summary": {
            "total_calls": len(calls),
            "agent_calls": len(agent_calls),
            "function_calls": len(function_calls),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "total_execution_time_ms": total_execution_time_ms,
        },
    }
