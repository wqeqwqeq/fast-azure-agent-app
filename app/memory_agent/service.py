"""Memory service for conversation context management."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import asyncpg
from agent_framework import ChatMessage, Role

from app.opsagent.model_registry import ModelName, ModelRegistry

from .agent import create_memory_agent
from .backend import MemoryBackend
from .schemas import ConversationContext, MemorySummaryOutput

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for managing conversation memory.

    Handles:
    - Reading memory from PostgreSQL
    - Triggering background summarization when needed
    - Providing conversation context (memory + rolling window)

    Configuration:
    - rolling_window: Number of recent messages to keep (default: 14 = 7 rounds)
    - summarize_threshold: Start summarizing after N rounds (default: 4)
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        registry: Optional[ModelRegistry] = None,
        model_name: Optional[ModelName] = None,
        rolling_window: int = 14,
        summarize_threshold: int = 4,
    ):
        """Initialize memory service.

        Args:
            pool: asyncpg connection pool
            registry: ModelRegistry for agent creation
            model_name: Model to use for summarization (e.g., "gpt-4.1-mini")
            rolling_window: Number of recent messages to keep in context
            summarize_threshold: Start summarizing after this many rounds
        """
        self.backend = MemoryBackend(pool)
        self.registry = registry
        self.model_name = model_name
        self.rolling_window = rolling_window
        self.summarize_threshold = summarize_threshold
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def get_context_for_workflow(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
    ) -> ConversationContext:
        """Get conversation context for workflow execution.

        This is the main entry point called from messages.py.
        Uses existing memory (if any) + rolling window of recent messages.

        Race condition handling:
        - Uses last computed memory even if summarization is in progress
        - Falls back to: previous memory + unsummarized raw messages
        - No context is ever lost

        Args:
            conversation_id: Conversation ID
            messages: Full message list from conversation

        Returns:
            ConversationContext with memory and recent messages
        """
        total_messages = len(messages)

        # Rounds 1-3: No summarization, use all raw messages
        # threshold=4 means we start summarizing at round 4 (8 messages)
        if total_messages < self.summarize_threshold * 2:
            return ConversationContext(
                memory_text=None,
                recent_messages=messages,
            )

        # Get latest memory from DB (may not cover all old messages due to race)
        latest_memory = await self.backend.get_latest_memory(conversation_id)

        if latest_memory:
            # Use memory + messages after end_sequence
            covered_until = latest_memory.end_sequence + 1
            uncovered_messages = [
                m for i, m in enumerate(messages) if i >= covered_until
            ]

            # Apply rolling window to uncovered messages if too many
            if len(uncovered_messages) > self.rolling_window:
                recent = uncovered_messages[-self.rolling_window:]
            else:
                recent = uncovered_messages

            return ConversationContext(
                memory_text=latest_memory.memory_text,
                recent_messages=recent,
            )
        else:
            # No memory yet, use rolling window of raw messages
            if len(messages) > self.rolling_window:
                recent = messages[-self.rolling_window:]
            else:
                recent = messages

            return ConversationContext(
                memory_text=None,
                recent_messages=recent,
            )

    def trigger_summarization_if_needed(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
    ) -> None:
        """Check if summarization is needed and trigger background task.

        Called after saving conversation. Runs in background to not block response.

        Summarization logic:
        - Only trigger if total messages >= threshold * 2 (e.g., 8 for threshold=4)
        - Only summarize messages not yet summarized
        - Summarize in pairs (user + assistant) to maintain context

        Args:
            conversation_id: Conversation ID
            messages: Full message list
        """
        total_messages = len(messages)

        # Skip if not enough messages (rounds 1-3)
        if total_messages < self.summarize_threshold * 2:
            return

        # Skip if already processing this conversation
        if conversation_id in self._active_tasks:
            task = self._active_tasks[conversation_id]
            if not task.done():
                logger.debug(f"Summarization already in progress for {conversation_id}")
                return

        # Create and track background task
        task = asyncio.create_task(
            self._summarize_with_timing(conversation_id, messages)
        )
        self._active_tasks[conversation_id] = task

        # Clean up when done
        def cleanup(t: asyncio.Task) -> None:
            self._active_tasks.pop(conversation_id, None)
            if t.exception():
                logger.error(f"Summarization task failed: {t.exception()}")

        task.add_done_callback(cleanup)

    async def _summarize_with_timing(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
    ) -> None:
        """Background task to summarize messages with timing.

        Args:
            conversation_id: Conversation ID
            messages: Full message list
        """
        start_time = time.monotonic()
        try:
            # Get existing memory to know what's already summarized
            existing_memory = await self.backend.get_latest_memory(conversation_id)
            already_summarized_until = (
                existing_memory.end_sequence if existing_memory else -1
            )

            total_messages = len(messages)

            # Calculate how many messages can be summarized
            # Keep rolling_window messages for recent context
            summarizable_count = max(0, total_messages - self.rolling_window)

            # Nothing new to summarize
            if summarizable_count <= already_summarized_until + 1:
                logger.debug(f"No new messages to summarize for {conversation_id}")
                return

            # Determine messages to summarize in this batch
            # Always summarize in pairs (user + assistant)
            start_sequence = already_summarized_until + 1
            end_sequence = summarizable_count - 1

            # Ensure we have at least 2 messages (1 pair)
            if end_sequence - start_sequence < 1:
                return

            # Round to pairs
            messages_count = end_sequence - start_sequence + 1
            if messages_count % 2 != 0:
                end_sequence -= 1  # Drop last message to keep pairs

            if end_sequence < start_sequence:
                return

            messages_to_summarize = messages[start_sequence : end_sequence + 1]

            # Create agent and generate summary
            agent = create_memory_agent(self.registry, self.model_name)

            # Format messages for agent
            conversation_text = "\n".join(
                [
                    f"{msg['role'].capitalize()}: {msg['content']}"
                    for msg in messages_to_summarize
                ]
            )

            # Include existing memory if present
            if existing_memory and existing_memory.memory_text:
                prompt = f"""Previous context summary:
{existing_memory.memory_text}

New conversation segment to incorporate:
{conversation_text}

Create an updated summary that combines the previous context with the new information."""
            else:
                prompt = f"""Conversation segment to summarize:
{conversation_text}"""

            # Run agent
            response = await agent.run(
                messages=[ChatMessage(Role.USER, text=prompt)]
            )

            # Parse response
            summary_output = MemorySummaryOutput.model_validate_json(response.text)

            # Calculate generation time
            generation_time_ms = int((time.monotonic() - start_time) * 1000)

            # Save to database (only if non-empty)
            if summary_output.summary and summary_output.summary.strip():
                await self.backend.insert_memory(
                    conversation_id=conversation_id,
                    memory_text=summary_output.summary,
                    start_sequence=start_sequence,
                    end_sequence=end_sequence,
                    generation_time_ms=generation_time_ms,
                )

                logger.info(
                    f"Summarized messages {start_sequence}-{end_sequence} "
                    f"for {conversation_id} in {generation_time_ms}ms"
                )

        except Exception as e:
            logger.error(f"Failed to summarize messages for {conversation_id}: {e}")
            # Don't re-raise - background task failures shouldn't crash the app
