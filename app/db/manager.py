"""Async chat history manager with PostgreSQL + Redis write-through caching."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .postgresql import AsyncPostgreSQLBackend
from .redis import AsyncRedisBackend

logger = logging.getLogger(__name__)


class AsyncChatHistoryManager:
    """Async manager for chat history storage with write-through caching.

    This manager orchestrates PostgreSQL (primary storage) and Redis (cache):
    - Write-through: Write to PostgreSQL first, then update Redis cache
    - Cache-aside reads: Try Redis first, fallback to PostgreSQL on miss
    """

    def __init__(self, history_days: int = 7) -> None:
        """Initialize chat history manager.

        Args:
            history_days: Number of days of history to load
        """
        self.history_days = history_days
        self.backend: Optional[AsyncPostgreSQLBackend] = None
        self.cache: Optional[AsyncRedisBackend] = None
        self._use_cache: bool = False

    async def initialize(
        self,
        postgres_connection_string: str,
        redis_host: Optional[str] = None,
        redis_password: Optional[str] = None,
        redis_port: int = 6380,
        redis_ssl: bool = True,
        redis_ttl: int = 1800,
    ) -> None:
        """Initialize database connections.

        Args:
            postgres_connection_string: PostgreSQL connection string
            redis_host: Redis server hostname (optional, for caching)
            redis_password: Redis password (optional)
            redis_port: Redis port (default: 6380)
            redis_ssl: Enable SSL/TLS (default: True)
            redis_ttl: TTL for Redis keys in seconds (default: 1800)
        """
        # Initialize PostgreSQL (required)
        self.backend = AsyncPostgreSQLBackend()
        await self.backend.connect(postgres_connection_string)

        # Initialize Redis (optional cache)
        if redis_host and redis_password:
            try:
                self.cache = AsyncRedisBackend()
                await self.cache.connect(
                    redis_host=redis_host,
                    redis_password=redis_password,
                    redis_port=redis_port,
                    redis_ssl=redis_ssl,
                    redis_ttl=redis_ttl,
                )
                self._use_cache = True
                logger.info("Redis cache enabled")
            except Exception as e:
                logger.warning(f"Redis cache unavailable, continuing without cache: {e}")
                self.cache = None
                self._use_cache = False
        else:
            logger.info("Redis not configured, running without cache")

    async def close(self) -> None:
        """Close all database connections."""
        if self.backend:
            await self.backend.close()
        if self.cache:
            await self.cache.close()

    async def list_conversations(
        self, user_id: str
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Return list of (conversation_id, conversation) from storage.

        Cache-aside read: Try Redis first, fallback to PostgreSQL on miss.

        Args:
            user_id: User client ID

        Returns:
            List of (conversation_id, conversation_dict) tuples
        """
        if not self.backend:
            raise RuntimeError("Database not initialized")

        # Try cache first
        if self._use_cache and self.cache and self.cache.is_available():
            cached = await self.cache.get_conversations_list(user_id, self.history_days)
            if cached is not None:
                return cached
            logger.info(f"Cache miss for user {user_id}, loading from PostgreSQL")

        # Load from PostgreSQL
        conversations = await self.backend.list_conversations(user_id, days=self.history_days)

        # Populate cache
        if self._use_cache and self.cache and self.cache.is_available():
            await self.cache.set_conversations_list(user_id, conversations)

        return conversations

    async def get_conversation(
        self, conversation_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Load and return a single conversation, or None if missing.

        Cache-aside read: Try Redis first, fallback to PostgreSQL on miss.

        Args:
            conversation_id: Conversation ID
            user_id: User client ID

        Returns:
            Conversation dict or None
        """
        if not self.backend:
            raise RuntimeError("Database not initialized")

        # Try cache first
        if self._use_cache and self.cache and self.cache.is_available():
            cached = await self.cache.get_conversation_messages(conversation_id, user_id)
            if cached is not None:
                return cached
            logger.info(f"Cache miss for conversation {conversation_id}")

        # Load from PostgreSQL
        conversation = await self.backend.get_conversation(conversation_id, user_id)

        # Populate cache
        if conversation and self._use_cache and self.cache and self.cache.is_available():
            await self.cache.set_conversation_messages(conversation_id, conversation["messages"])

        return conversation

    async def save_conversation(
        self, conversation_id: str, user_id: str, conversation: Dict[str, Any]
    ) -> None:
        """Persist a conversation atomically to storage.

        Write-through: Write to PostgreSQL first, then update Redis cache.

        Args:
            conversation_id: Conversation ID
            user_id: User client ID
            conversation: Conversation dict
        """
        if not self.backend:
            raise RuntimeError("Database not initialized")

        # 1. Write to PostgreSQL first (source of truth)
        await self.backend.save_conversation(conversation_id, user_id, conversation)

        # 2. Update Redis cache
        if self._use_cache and self.cache and self.cache.is_available():
            # Update conversation metadata (for conversation list)
            await self.cache.update_conversation_metadata(user_id, conversation_id, conversation)

            # Append new messages (efficient)
            # Check how many messages are already cached
            try:
                redis_msg_count = await self.cache.get_message_count(conversation_id)
                new_messages = conversation["messages"][redis_msg_count:]
                if new_messages:
                    # Append with correct sequence numbering
                    await self.cache.append_messages(
                        conversation_id, new_messages, start_sequence=redis_msg_count
                    )
                elif redis_msg_count == 0:
                    # No messages cached yet, cache all
                    await self.cache.set_conversation_messages(
                        conversation_id, conversation["messages"]
                    )
            except Exception as e:
                logger.warning(f"Failed to update cache: {e}")

    async def delete_conversation(
        self, conversation_id: str, user_id: str
    ) -> None:
        """Remove a conversation from storage.

        Write-through: Delete from PostgreSQL first, then invalidate cache.

        Args:
            conversation_id: Conversation ID
            user_id: User client ID
        """
        if not self.backend:
            raise RuntimeError("Database not initialized")

        # 1. Delete from PostgreSQL first
        await self.backend.delete_conversation(conversation_id, user_id)

        # 2. Invalidate cache
        if self._use_cache and self.cache and self.cache.is_available():
            await self.cache.delete_conversation_cache(user_id, conversation_id)
