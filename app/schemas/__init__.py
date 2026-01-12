"""Pydantic schemas for API requests and responses."""

from .conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageSchema,
)
from .evaluation import EvaluationResponse, EvaluationUpdate
from .message import SendMessageRequest
from .models import AgentsResponse, ModelsResponse
from .settings import SettingsResponse
from .user import UserInfo

__all__ = [
    # Conversation schemas
    "MessageSchema",
    "ConversationCreate",
    "ConversationUpdate",
    "ConversationResponse",
    # Message schemas
    "SendMessageRequest",
    # Evaluation schemas
    "EvaluationUpdate",
    "EvaluationResponse",
    # User schemas
    "UserInfo",
    # Settings schemas
    "SettingsResponse",
    # Model schemas
    "ModelsResponse",
    "AgentsResponse",
]
