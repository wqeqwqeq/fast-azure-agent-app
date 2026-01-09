"""Pydantic schemas for API requests and responses."""

from .conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageSchema,
)
from .evaluation import EvaluationResponse, EvaluationUpdate
from .events import (
    AgentFinishedEvent,
    AgentInvokedEvent,
    FunctionEndEvent,
    FunctionStartEvent,
)
from .message import SendMessageRequest, SendMessageResponse
from .settings import ModelsResponse, SettingsResponse
from .user import UserInfo

__all__ = [
    # Conversation schemas
    "MessageSchema",
    "ConversationCreate",
    "ConversationUpdate",
    "ConversationResponse",
    "ConversationListResponse",
    # Message schemas
    "SendMessageRequest",
    "SendMessageResponse",
    # Evaluation schemas
    "EvaluationUpdate",
    "EvaluationResponse",
    # User schemas
    "UserInfo",
    # Settings schemas
    "SettingsResponse",
    "ModelsResponse",
    # Event schemas
    "FunctionStartEvent",
    "FunctionEndEvent",
    "AgentInvokedEvent",
    "AgentFinishedEvent",
]
