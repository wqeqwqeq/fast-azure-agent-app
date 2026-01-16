"""Conversation CRUD API routes."""

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..dependencies import CurrentUserDep, HistoryManagerDep
from ..schemas import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
)

router = APIRouter()


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    history: HistoryManagerDep,
    current_user: CurrentUserDep,
) -> List[ConversationResponse]:
    """List all conversations for the current user, sorted by last_modified (newest first).

    Returns:
        List of conversations with metadata (messages may be empty for lazy loading)
    """
    user_id = current_user.user_id

    # Get conversations from storage
    conversations = await history.list_conversations(user_id)

    # Sort by last_modified DESC (newest first)
    sorted_convos = sorted(
        conversations,
        key=lambda x: x[1].get("last_modified", x[1].get("created_at", "")),
        reverse=True,
    )

    # Convert to response model
    return [
        ConversationResponse(
            id=cid,
            title=convo.get("title", "New chat"),
            model=convo.get("model", get_settings().default_model),
            created_at=convo.get("created_at", ""),
            last_modified=convo.get("last_modified", ""),
            messages=[],  # May be empty for lazy-loaded list
        )
        for cid, convo in sorted_convos
    ]


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    history: HistoryManagerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    """Create a new conversation.

    Args:
        body: ConversationCreate with optional model specification

    Returns:
        Created conversation with generated ID
    """
    user_id = current_user.user_id
    settings = get_settings()

    cid = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()

    conversation = {
        "title": "New chat",
        "model": body.model or settings.default_model,
        "messages": [],
        "created_at": now,
        "last_modified": now,
    }

    await history.save_conversation(cid, user_id, conversation)

    return ConversationResponse(
        id=cid,
        title=conversation["title"],
        model=conversation["model"],
        messages=[],
        created_at=conversation["created_at"],
        last_modified=conversation["last_modified"],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    history: HistoryManagerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    """Get a specific conversation with all messages.

    Args:
        conversation_id: Conversation ID

    Returns:
        Conversation with all messages

    Raises:
        HTTPException: 404 if conversation not found
    """
    user_id = current_user.user_id

    convo = await history.get_conversation(conversation_id, user_id)

    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse(
        id=conversation_id,
        title=convo.get("title", "New chat"),
        model=convo.get("model", get_settings().default_model),
        messages=[
            {"role": m["role"], "content": m["content"], "time": m.get("time")}
            for m in convo.get("messages", [])
        ],
        created_at=convo.get("created_at", ""),
        last_modified=convo.get("last_modified", ""),
        agent_level_llm_overwrite=convo.get("agent_level_llm_overwrite"),
    )


@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    history: HistoryManagerDep,
    current_user: CurrentUserDep,
) -> ConversationResponse:
    """Update a conversation (e.g., rename, change model).

    Note: Does not update last_modified timestamp for metadata changes.

    Args:
        conversation_id: Conversation ID
        body: ConversationUpdate with optional title/model changes

    Returns:
        Updated conversation

    Raises:
        HTTPException: 404 if conversation not found
    """
    user_id = current_user.user_id

    convo = await history.get_conversation(conversation_id, user_id)

    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Update title (don't update last_modified for rename)
    if body.title is not None:
        convo["title"] = body.title

    # Update model (don't update last_modified for model change)
    if body.model is not None:
        convo["model"] = body.model

    await history.save_conversation(conversation_id, user_id, convo)

    return ConversationResponse(
        id=conversation_id,
        title=convo["title"],
        model=convo["model"],
        messages=[
            {"role": m["role"], "content": m["content"], "time": m.get("time")}
            for m in convo.get("messages", [])
        ],
        created_at=convo.get("created_at", ""),
        last_modified=convo.get("last_modified", ""),
        agent_level_llm_overwrite=convo.get("agent_level_llm_overwrite"),
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    history: HistoryManagerDep,
    current_user: CurrentUserDep,
) -> None:
    """Delete a conversation.

    Args:
        conversation_id: Conversation ID
    """
    user_id = current_user.user_id
    await history.delete_conversation(conversation_id, user_id)
