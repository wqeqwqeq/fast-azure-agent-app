"""Async Redis cache backend for chat history storage."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class AsyncRedisBackend:
    """Async Redis cache backend (independent of PostgreSQL coupling)."""

    def __init__(self) -> None:
        """Initialize Redis backend (connection created via connect())."""
        self.redis_client: Optional[redis.Redis] = None
        self.redis_ttl: int = 1800  # Default 30 minutes

    async def connect(
        self,
        redis_host: str,
        redis_password: str,
        redis_port: int = 6380,
        redis_ssl: bool = True,
        redis_ttl: int = 1800,
    ) -> None:
        """Create async Redis connection.

        Args:
            redis_host: Redis server hostname
            redis_password: Redis password/access key
            redis_port: Redis port (default: 6380 for Azure SSL)
            redis_ssl: Enable SSL/TLS connection (default: True for Azure)
            redis_ttl: TTL for Redis keys in seconds (default: 1800 = 30 minutes)
        """
        self.redis_ttl = redis_ttl

        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                ssl=redis_ssl,
                ssl_cert_reqs="required" if redis_ssl else None,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                max_connections=10,
            )
            # Test connection
            await self.redis_client.ping()
            logger.info(f"Redis connection successful: {redis_host}:{redis_port}")
        except redis.RedisError as e:
            logger.error(f"Redis connection failed: {e}")
            self.redis_client = None
            raise RuntimeError(f"Failed to connect to Redis: {e}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.aclose()
            logger.info("Redis connection closed")

    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self.redis_client is not None

    async def get_conversations_list(
        self, user_id: str, days: int = 7
    ) -> Optional[List[Tuple[str, Dict[str, Any]]]]:
        """Get cached conversations list. Returns None if cache miss.

        Args:
            user_id: User client ID
            days: Number of days of history to filter

        Returns:
            List of (conversation_id, conversation_dict) tuples or None
        """
        if not self.redis_client:
            return None

        conv_key = f"chat:{user_id}:conversations"

        try:
            raw_data = await self.redis_client.zrevrange(conv_key, 0, -1)
            if raw_data:
                # Parse JSON and filter by days
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                conversations = []

                for json_str in raw_data:
                    meta = json.loads(json_str)
                    created_at = datetime.fromisoformat(meta["created_at"])
                    if created_at >= cutoff:
                        conversations.append((
                            meta["conversation_id"],
                            {
                                "title": meta["title"],
                                "model": meta["model"],
                                "messages": [],  # Lazy load
                                "created_at": meta["created_at"],
                                "last_modified": meta["last_modified"],
                            },
                        ))

                # Refresh TTL
                await self.redis_client.expire(conv_key, self.redis_ttl)
                logger.info(f"Redis cache hit for user {user_id}: {len(conversations)} conversations")
                return conversations
        except redis.RedisError as e:
            logger.warning(f"Redis error in get_conversations_list: {e}")

        return None  # Cache miss or error

    async def set_conversations_list(
        self, user_id: str, conversations: List[Tuple[str, Dict[str, Any]]]
    ) -> bool:
        """Cache conversations list in Redis.

        Args:
            user_id: User client ID
            conversations: List of (conversation_id, conversation_dict) tuples

        Returns:
            True if successful, False otherwise
        """
        if not self.redis_client:
            return False

        conv_key = f"chat:{user_id}:conversations"

        try:
            async with self.redis_client.pipeline(transaction=True) as pipeline:
                for cid, convo in conversations:
                    json_meta = json.dumps({
                        "conversation_id": cid,
                        "title": convo["title"],
                        "model": convo["model"],
                        "created_at": convo["created_at"],
                        "last_modified": convo["last_modified"],
                    })
                    score = datetime.fromisoformat(convo["last_modified"]).timestamp()
                    pipeline.zadd(conv_key, {json_meta: score})
                pipeline.expire(conv_key, self.redis_ttl)
                await pipeline.execute()
            logger.info(f"Cached {len(conversations)} conversations for user {user_id}")
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis write error in set_conversations_list: {e}")
            return False

    async def get_conversation_messages(
        self, conversation_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached conversation messages. Returns None if cache miss.

        Args:
            conversation_id: Conversation ID
            user_id: User client ID

        Returns:
            Conversation dict with messages or None
        """
        if not self.redis_client:
            return None

        msg_key = f"chat:{conversation_id}:messages"
        conv_key = f"chat:{user_id}:conversations"

        try:
            messages_json = await self.redis_client.lrange(msg_key, 0, -1)

            if messages_json:
                # Verify ownership by checking metadata
                all_convos = await self.redis_client.zrevrange(conv_key, 0, -1)
                meta = None
                for json_str in all_convos:
                    temp_meta = json.loads(json_str)
                    if temp_meta["conversation_id"] == conversation_id:
                        meta = temp_meta
                        break

                if meta:
                    # Refresh TTLs
                    async with self.redis_client.pipeline(transaction=True) as pipeline:
                        pipeline.expire(msg_key, self.redis_ttl)
                        pipeline.expire(conv_key, self.redis_ttl)
                        await pipeline.execute()

                    logger.info(f"Redis cache hit for conversation {conversation_id}")
                    return {
                        "title": meta["title"],
                        "model": meta["model"],
                        "messages": [json.loads(msg) for msg in messages_json],
                        "created_at": meta["created_at"],
                        "last_modified": meta["last_modified"],
                        **({"agent_level_llm_overwrite": meta["agent_level_llm_overwrite"]} if meta.get("agent_level_llm_overwrite") else {}),
                    }
        except redis.RedisError as e:
            logger.warning(f"Redis error in get_conversation_messages: {e}")

        return None  # Cache miss or error

    async def set_conversation_messages(
        self, conversation_id: str, messages: List[Dict[str, Any]]
    ) -> bool:
        """Cache conversation messages in Redis.

        Args:
            conversation_id: Conversation ID
            messages: List of message dicts

        Returns:
            True if successful, False otherwise
        """
        if not self.redis_client:
            return False

        msg_key = f"chat:{conversation_id}:messages"

        try:
            async with self.redis_client.pipeline(transaction=True) as pipeline:
                # Delete existing messages first
                pipeline.delete(msg_key)
                for idx, msg in enumerate(messages):
                    # Ensure sequence_number is included
                    msg_with_seq = {
                        "sequence_number": idx,
                        "role": msg["role"],
                        "content": msg["content"],
                        "time": msg.get("time", datetime.now(timezone.utc).isoformat()),
                    }
                    pipeline.rpush(msg_key, json.dumps(msg_with_seq))
                pipeline.expire(msg_key, self.redis_ttl)
                await pipeline.execute()
            logger.info(f"Cached {len(messages)} messages for conversation {conversation_id}")
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis write error in set_conversation_messages: {e}")
            return False

    async def update_conversation_metadata(
        self, user_id: str, conversation_id: str, conversation: Dict[str, Any]
    ) -> bool:
        """Update conversation metadata in sorted set.

        Args:
            user_id: User client ID
            conversation_id: Conversation ID
            conversation: Conversation dict with metadata

        Returns:
            True if successful, False otherwise
        """
        if not self.redis_client:
            return False

        conv_key = f"chat:{user_id}:conversations"

        try:
            # Remove old entry first (metadata might have changed)
            all_convos = await self.redis_client.zrevrange(conv_key, 0, -1)

            async with self.redis_client.pipeline(transaction=True) as pipeline:
                for json_str in all_convos:
                    meta = json.loads(json_str)
                    if meta["conversation_id"] == conversation_id:
                        pipeline.zrem(conv_key, json_str)
                        break

                # Add new metadata
                json_meta = json.dumps({
                    "conversation_id": conversation_id,
                    "title": conversation["title"],
                    "model": conversation["model"],
                    "created_at": conversation["created_at"],
                    "last_modified": conversation["last_modified"],
                    **({"agent_level_llm_overwrite": conversation["agent_level_llm_overwrite"]} if conversation.get("agent_level_llm_overwrite") else {}),
                })
                score = datetime.fromisoformat(conversation["last_modified"]).timestamp()
                pipeline.zadd(conv_key, {json_meta: score})
                pipeline.expire(conv_key, self.redis_ttl)
                await pipeline.execute()

            logger.info(f"Updated metadata for conversation {conversation_id}")
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis error in update_conversation_metadata: {e}")
            return False

    async def append_messages(
        self, conversation_id: str, new_messages: List[Dict[str, Any]], start_sequence: int = 0
    ) -> bool:
        """Append new messages to existing cached conversation.

        Args:
            conversation_id: Conversation ID
            new_messages: List of new message dicts to append
            start_sequence: Starting sequence number for new messages

        Returns:
            True if successful, False otherwise
        """
        if not self.redis_client:
            return False

        msg_key = f"chat:{conversation_id}:messages"

        try:
            async with self.redis_client.pipeline(transaction=True) as pipeline:
                for idx, msg in enumerate(new_messages):
                    msg_with_seq = {
                        "sequence_number": start_sequence + idx,
                        "role": msg["role"],
                        "content": msg["content"],
                        "time": msg.get("time", datetime.now(timezone.utc).isoformat()),
                    }
                    pipeline.rpush(msg_key, json.dumps(msg_with_seq))
                pipeline.expire(msg_key, self.redis_ttl)
                await pipeline.execute()
            logger.info(f"Appended {len(new_messages)} messages to conversation {conversation_id}")
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis error in append_messages: {e}")
            return False

    async def delete_conversation_cache(
        self, user_id: str, conversation_id: str
    ) -> bool:
        """Delete conversation from Redis cache.

        Args:
            user_id: User client ID
            conversation_id: Conversation ID

        Returns:
            True if successful, False otherwise
        """
        if not self.redis_client:
            return False

        conv_key = f"chat:{user_id}:conversations"
        msg_key = f"chat:{conversation_id}:messages"

        try:
            # Find and remove from sorted set
            all_convos = await self.redis_client.zrevrange(conv_key, 0, -1)

            async with self.redis_client.pipeline(transaction=True) as pipeline:
                for json_str in all_convos:
                    meta = json.loads(json_str)
                    if meta["conversation_id"] == conversation_id:
                        pipeline.zrem(conv_key, json_str)
                        break

                # Delete messages
                pipeline.delete(msg_key)
                await pipeline.execute()

            logger.info(f"Deleted cache for conversation {conversation_id}")
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis error in delete_conversation_cache: {e}")
            return False

    async def get_message_count(self, conversation_id: str) -> int:
        """Get the number of cached messages for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Number of cached messages, or 0 if not available
        """
        if not self.redis_client:
            return 0

        msg_key = f"chat:{conversation_id}:messages"
        try:
            return await self.redis_client.llen(msg_key) or 0
        except redis.RedisError:
            return 0
