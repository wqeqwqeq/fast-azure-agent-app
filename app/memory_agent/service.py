"""Memory service for conversation context management."""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import asyncpg
from agent_framework import ChatMessage, Role

from app.opsagent.model_registry import ModelName, ModelRegistry

from .agent import create_memory_agent
from .backend import MemoryBackend
from .schemas import ConversationContext, ImportantEntity, StructuredMemory

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for managing conversation memory with sliding window.

    Handles:
    - Reading memory from PostgreSQL (status='completed' only)
    - Triggering background summarization when needed
    - Providing conversation context (memory + gap messages)
    - Database-based concurrency control via status field

    Configuration:
    - rolling_window_size: Number of messages in sliding window (default: 14)
    - summarize_after_seq: Start summarizing when end_seq >= this (default: 5)
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        registry: Optional[ModelRegistry] = None,
        model_name: Optional[ModelName] = None,
        rolling_window_size: int = 14,
        summarize_after_seq: int = 5,
    ):
        """Initialize memory service.

        Args:
            pool: asyncpg connection pool
            registry: ModelRegistry for agent creation
            model_name: Model to use for summarization (e.g., "gpt-4.1-mini")
            rolling_window_size: Number of messages in sliding window
            summarize_after_seq: Start summarizing when end_seq >= this value
        """
        self.backend = MemoryBackend(pool)
        self.registry = registry
        self.model_name = model_name
        self.rolling_window_size = rolling_window_size
        self.summarize_after_seq = summarize_after_seq

    def _calculate_summary_range(self, last_saved_seq: int) -> tuple[int, int]:
        """Calculate the sliding window range for summarization.

        Args:
            last_saved_seq: Last saved message sequence number

        Returns:
            Tuple of (start_seq, end_seq) for the window
        """
        end_seq = last_saved_seq
        start_seq = max(0, end_seq - self.rolling_window_size + 1)

        # Ensure start_seq is even (don't split user/assistant pairs)
        if start_seq % 2 != 0:
            start_seq = start_seq + 1

        return (start_seq, end_seq)

    def _parse_memory_text(self, memory_text: str) -> Optional[StructuredMemory]:
        """Parse memory_text JSON string to StructuredMemory.

        Args:
            memory_text: JSON string from database

        Returns:
            StructuredMemory if valid JSON, None otherwise
        """
        if not memory_text:
            return None
        try:
            data = json.loads(memory_text)
            return StructuredMemory.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse memory_text as JSON: {e}")
            # Backward compatibility: treat as plain text fact
            return StructuredMemory(facts=[memory_text])

    def _format_structured_memory(self, memory: StructuredMemory) -> str:
        """Format StructuredMemory to natural language.

        Args:
            memory: Parsed structured memory

        Returns:
            Natural language representation
        """
        parts = []

        if memory.facts:
            parts.append("Facts: " + "; ".join(memory.facts))

        if memory.decisions:
            parts.append("Decisions: " + "; ".join(memory.decisions))

        if memory.user_preferences:
            parts.append("User preferences: " + "; ".join(memory.user_preferences))

        if memory.entities:
            entity_strs = []
            for e in memory.entities:
                if e.notes:
                    entity_strs.append(f"{e.name} ({e.notes})")
                else:
                    entity_strs.append(e.name)
            if entity_strs:
                parts.append("Entities: " + "; ".join(entity_strs))

        if memory.open_questions:
            parts.append("Open questions: " + "; ".join(memory.open_questions))

        return "\n".join(parts)

    def format_context_for_workflow(
        self,
        context: ConversationContext,
    ) -> str:
        """Format memory + chat history with XML tags for OpsAgent.

        Args:
            context: ConversationContext with memory and gap_messages

        Returns:
            Formatted string with XML tags, or empty string if no context
        """
        parts = []
        explanations = []

        # 1. Memory section (if exists)
        if context.memory:
            memory_text = self._format_structured_memory(context.memory)
            if memory_text:
                parts.append(f"<memory>\n{memory_text}\n</memory>")
                explanations.append("<memory>: Summarized key information from older messages")

        # 2. Chat history section (if any gap messages)
        if context.gap_messages:
            history_text = "\n".join([
                f"{msg['role'].capitalize()}: {msg['content']}"
                for msg in context.gap_messages
            ])
            parts.append(f"<chat_history>\n{history_text}\n</chat_history>")
            if context.memory:
                explanations.append("<chat_history>: Recent messages not yet summarized")
            else:
                explanations.append("<chat_history>: Previous messages in this conversation")

        # 3. If nothing, return empty
        if not parts:
            return ""

        # 4. Add explanation
        explanation = "The above provides context from this conversation:\n- " + "\n- ".join(explanations)
        return "\n".join(parts) + "\n\n" + explanation

    async def get_context_for_workflow(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
    ) -> ConversationContext:
        """Get conversation context for workflow execution.

        Called at the START of each round. Returns latest completed memory
        plus gap messages (messages after memory but before current user message).

        Args:
            conversation_id: Conversation ID
            messages: Full message list from conversation

        Returns:
            ConversationContext with memory and gap_messages
        """
        # Get latest COMPLETED memory only
        latest_memory = await self.backend.get_latest_memory(
            conversation_id, status="completed"
        )

        if latest_memory:
            # Parse the JSON memory_text
            memory = self._parse_memory_text(latest_memory.memory_text)

            # Calculate gap: messages after memory but before current user message
            gap_start = latest_memory.end_sequence + 1
            gap_end = len(messages) - 2  # exclude current user message
            if gap_end >= gap_start:
                gap_messages = messages[gap_start : gap_end + 1]
            else:
                gap_messages = []

            return ConversationContext(
                memory=memory,
                gap_messages=gap_messages,
            )
        else:
            # Fallback: use raw messages (no memory ready yet)
            # Exclude current user message
            if len(messages) > 1:
                gap_messages = messages[:-1]
            else:
                gap_messages = []

            return ConversationContext(
                memory=None,
                gap_messages=gap_messages,
            )

    async def trigger_summarization_if_needed(
        self,
        conversation_id: str,
        last_saved_seq: int,
        messages: List[Dict[str, Any]],
    ) -> None:
        """Check if summarization is needed and trigger background task.

        Called at the END of each round after saving the assistant message.
        Uses database status field for concurrency control.

        Args:
            conversation_id: Conversation ID
            last_saved_seq: Sequence number of the last saved message
            messages: Full message list for summarization
        """
        # Check if enough messages
        if last_saved_seq < self.summarize_after_seq:
            logger.debug(
                f"Not enough messages to summarize for {conversation_id}: "
                f"seq {last_saved_seq} < threshold {self.summarize_after_seq}"
            )
            return

        # Check if already processing (database-based concurrency control)
        if await self.backend.exists_processing(conversation_id):
            logger.debug(f"Summarization already in progress for {conversation_id}")
            return

        # Calculate sliding window range
        start_seq, end_seq = self._calculate_summary_range(last_saved_seq)

        # Get latest completed memory for base_memory_id
        latest_memory = await self.backend.get_latest_memory(
            conversation_id, status="completed"
        )
        base_memory_id = latest_memory.memory_id if latest_memory else None

        # Log if window is sliding
        if start_seq > 0:
            logger.info(
                f"Sliding window: dropping seq 0-{start_seq - 1} for {conversation_id}"
            )

        # Insert 'processing' record BEFORE starting background task
        try:
            memory_id = await self.backend.insert_memory(
                conversation_id=conversation_id,
                memory_text="",  # Empty for processing status
                start_sequence=start_seq,
                end_sequence=end_seq,
                base_memory_id=base_memory_id,
                status="processing",
            )
        except Exception as e:
            logger.error(f"Failed to insert processing memory: {e}")
            return

        # Start background task
        asyncio.create_task(
            self._do_summarization(
                memory_id=memory_id,
                conversation_id=conversation_id,
                start_seq=start_seq,
                end_seq=end_seq,
                base_memory_id=base_memory_id,
                messages=messages,
            )
        )

    def _merge_entities(
        self,
        base: Optional[List[ImportantEntity]],
        new: Optional[List[ImportantEntity]],
    ) -> Optional[List[ImportantEntity]]:
        """Merge entity lists, updating existing entities with new info.

        Args:
            base: Base entity list
            new: New entity list

        Returns:
            Merged entity list
        """
        if not base and not new:
            return None
        if not base:
            return new
        if not new:
            return base

        # Build lookup by name
        merged = {e.name.lower(): e for e in base}
        for entity in new:
            key = entity.name.lower()
            if key in merged:
                # Update existing entity
                existing = merged[key]
                merged[key] = ImportantEntity(
                    name=entity.name,
                    aliases=list(set(existing.aliases + entity.aliases)),
                    notes=entity.notes or existing.notes,
                )
            else:
                merged[key] = entity

        result = list(merged.values())
        return result[:10] if result else None  # Limit to 10 entities

    def _merge_memories(
        self,
        base: Optional[StructuredMemory],
        new: StructuredMemory,
    ) -> StructuredMemory:
        """Merge two memories - combine lists with dedup.

        Args:
            base: Base memory (can be None)
            new: New memory to merge

        Returns:
            Merged StructuredMemory
        """
        if not base:
            return new

        def merge_list(a: Optional[List[str]], b: Optional[List[str]], limit: int = 10) -> Optional[List[str]]:
            combined = (a or []) + (b or [])
            # Simple dedup - keep unique, limit size
            seen = set()
            result = []
            for item in combined:
                if item not in seen:
                    seen.add(item)
                    result.append(item)
            return result[-limit:] if result else None

        return StructuredMemory(
            facts=merge_list(base.facts, new.facts),
            decisions=merge_list(base.decisions, new.decisions, limit=5),
            user_preferences=merge_list(base.user_preferences, new.user_preferences, limit=5),
            open_questions=new.open_questions,  # Only keep latest
            entities=self._merge_entities(base.entities, new.entities),
        )

    async def _do_summarization(
        self,
        memory_id: int,
        conversation_id: str,
        start_seq: int,
        end_seq: int,
        base_memory_id: Optional[int],
        messages: List[Dict[str, Any]],
    ) -> None:
        """Background task to perform summarization.

        Args:
            memory_id: The processing memory record ID
            conversation_id: Conversation ID
            start_seq: First message sequence in window
            end_seq: Last message sequence in window
            base_memory_id: Previous memory ID for incremental summarization
            messages: Full message list
        """
        start_time = time.monotonic()
        try:
            # Get base memory if exists
            base_memory: Optional[StructuredMemory] = None
            if base_memory_id:
                base_record = await self.backend.get_memory_by_id(base_memory_id)
                if base_record:
                    base_memory = self._parse_memory_text(base_record.memory_text)

            # Determine which messages to fetch
            if base_memory and base_memory_id:
                base_record = await self.backend.get_memory_by_id(base_memory_id)
                new_messages_start = base_record.end_sequence + 1 if base_record else start_seq
            else:
                new_messages_start = start_seq

            # Get messages to summarize
            new_messages = messages[new_messages_start : end_seq + 1]

            if not new_messages:
                logger.debug(f"No new messages to summarize for {conversation_id}")
                await self.backend.update_memory_status(memory_id, "failed")
                return

            # Create agent
            agent = create_memory_agent(self.registry, self.model_name)

            # Format messages for agent
            conversation_text = "\n".join([
                f"{msg['role'].capitalize()}: {msg['content']}"
                for msg in new_messages
            ])

            # Build prompt
            if base_memory:
                base_json = base_memory.model_dump_json(exclude_none=True)
                prompt = f"""Previous memory:
{base_json}

New messages to incorporate:
{conversation_text}

Extract and merge new information with the previous memory."""
            else:
                prompt = f"""Conversation messages:
{conversation_text}

Extract key information from this conversation."""

            # Run agent
            response = await agent.run(
                messages=[ChatMessage(Role.USER, text=prompt)]
            )

            # Parse response
            new_memory = StructuredMemory.model_validate_json(response.text)

            # Merge with base if exists
            final_memory = self._merge_memories(base_memory, new_memory)

            # Calculate generation time
            generation_time_ms = int((time.monotonic() - start_time) * 1000)

            # Serialize to JSON for storage
            memory_json = final_memory.model_dump_json(exclude_none=True)

            # Update memory record
            if memory_json and memory_json != "{}":
                await self.backend.update_memory_status(
                    memory_id=memory_id,
                    status="completed",
                    memory_text=memory_json,
                    generation_time_ms=generation_time_ms,
                )

                logger.info(
                    f"Summarized messages {start_seq}-{end_seq} "
                    f"for {conversation_id} in {generation_time_ms}ms"
                )
            else:
                await self.backend.update_memory_status(memory_id, "failed")
                logger.warning(f"Empty memory generated for {conversation_id}")

        except Exception as e:
            logger.error(f"Failed to summarize messages for {conversation_id}: {e}")
            try:
                await self.backend.update_memory_status(memory_id, "failed")
            except Exception as update_error:
                logger.error(f"Failed to update memory status to failed: {update_error}")
