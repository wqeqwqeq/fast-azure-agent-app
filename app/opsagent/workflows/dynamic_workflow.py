"""Dynamic Workflow with multi-agent orchestration and review loop.

This workflow implements:
- Dynamic planning with step-based execution (sequential/parallel/mixed)
- Review mechanism to ensure answer completeness
- Clarify mechanism for ambiguous queries
- Maximum iterations controlled via WorkflowBuilder
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from agent_framework import (
    ChatAgent,
    ChatMessage,
    Executor,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
)
from typing_extensions import Never
from agent_framework._workflows._events import AgentRunUpdateEvent

from ..agents.clarify_agent import create_clarify_agent
from ..agents.log_analytics_agent import create_log_analytics_agent
from ..agents.plan_agent import create_plan_agent
from ..agents.replan_agent import create_replan_agent
from ..agents.review_agent import create_review_agent
from ..agents.service_health_agent import create_service_health_agent
from ..agents.servicenow_agent import create_servicenow_agent
from ..agents.summary_agent import create_summary_agent
from ..model_registry import AgentModelMapping, ModelName, ModelRegistry, create_model_resolver
from ..schemas.clarify import ClarifyOutput
from ..schemas.common import WorkflowInput
from ..schemas.review import ReviewOutput
from ..schemas.triage_plan import PlanStep, TriagePlanOutput
from ..schemas.triage_replan import TriageReplanOutput


# === Internal Dataclasses for Workflow Routing ===
@dataclass
class ExecutionResult:
    """Result from a single agent execution."""

    agent: str
    question: str
    response: str


@dataclass
class PlanRequest:
    """Request to triage in plan mode (initial query)."""

    messages: list[ChatMessage]


@dataclass
class ReplanRequest:
    """Request to triage in replan mode (after review)."""

    original_query: str
    previous_results: dict[int, list[ExecutionResult]]
    missing_aspects: list[str]
    suggested_approach: str


@dataclass
class ReviewRequest:
    """Request for review executor."""

    execution_results: dict[int, list[ExecutionResult]]


@dataclass
class StreamingRequest:
    """Request for streaming summary output."""

    execution_results: dict[int, list[ExecutionResult]]


# === Input Processing ===
@executor(id="store_query")
async def store_query(
    input: WorkflowInput, ctx: WorkflowContext[PlanRequest]
) -> None:
    """Store conversation history and prepare for triage."""
    # Handle both input modes: query (DevUI) or messages (Flask)
    if input.messages:
        chat_messages = [
            ChatMessage(
                Role.USER if msg.role == "user" else Role.ASSISTANT,
                text=msg.text,
            )
            for msg in input.messages
        ]
    else:
        chat_messages = [ChatMessage(Role.USER, text=input.query)]

    # Store conversation history
    await ctx.set_shared_state("conversation_history", chat_messages)

    # Extract latest user query
    latest_query = ""
    for msg in reversed(chat_messages):
        if msg.role == Role.USER:
            latest_query = msg.text
            break
    await ctx.set_shared_state("original_query", latest_query)

    # Initialize retry flag
    await ctx.set_shared_state("is_retry", False)

    # Send to triage in plan mode
    await ctx.send_message(PlanRequest(messages=chat_messages))


# === Triage Executor (Plan + Replan modes) ===
class TriageExecutor(Executor):
    """Unified triage executor handling both plan and replan modes."""

    def __init__(
        self,
        plan_agent: ChatAgent,
        replan_agent: ChatAgent,
        id: str = "triage",
    ):
        super().__init__(id=id)
        self._plan_agent = plan_agent
        self._replan_agent = replan_agent

    @handler
    async def handle_plan(
        self, request: PlanRequest, ctx: WorkflowContext[TriagePlanOutput]
    ) -> None:
        """Process initial user query and generate execution plan."""
        prompt = self._build_plan_prompt(request.messages)

        response = await self._plan_agent.run(
            messages=[ChatMessage(Role.USER, text=prompt)]
        )

        output = TriagePlanOutput.model_validate_json(response.text)

        # Store plan for later reference
        await ctx.set_shared_state("current_plan", output.plan)

        await ctx.send_message(output)

    @handler
    async def handle_replan(
        self, request: ReplanRequest, ctx: WorkflowContext[TriageReplanOutput]
    ) -> None:
        """Process review feedback and decide on retry strategy."""
        prompt = self._build_replan_prompt(request)

        response = await self._replan_agent.run(
            messages=[ChatMessage(Role.USER, text=prompt)]
        )

        output = TriageReplanOutput.model_validate_json(response.text)

        # If retrying, mark as retry
        if output.action == "retry":
            await ctx.set_shared_state("is_retry", True)

        await ctx.send_message(output)

    def _build_plan_prompt(self, messages: list[ChatMessage]) -> str:
        """Build prompt for plan mode."""
        history = "\n".join(
            f"[{msg.role.value}]: {msg.text}" for msg in messages
        )
        return f"""Analyze this conversation and create an execution plan.

## Conversation History
{history}

## Instructions
Output a JSON object with the following schema:
- action: "plan" | "clarify" | "reject"
- reject_reason: string (if clarify or reject)
- plan: list of {{step, agent, question}}
- plan_reason: string

Remember: same step number = parallel, different step numbers = sequential."""

    def _build_replan_prompt(self, request: ReplanRequest) -> str:
        """Build prompt for replan mode."""
        results_str = self._format_execution_results(request.previous_results)

        return f"""The review agent found gaps in the response. Decide how to proceed.

## Original Query
{request.original_query}

## Previous Execution Results
{results_str}

## Review Feedback
- Missing aspects: {request.missing_aspects}
- Suggested approach: {request.suggested_approach}

## Instructions
Decide how to proceed: retry with new plan, request clarification, or reject feedback.
Output a JSON object:
- action: "retry" | "clarify" | "reject"
- new_plan: list of {{step, agent, question}} (if action is "retry")
- rejection_reason: string (if action is "reject")
- clarification_reason: string (if action is "clarify")

Be critical - only retry if the gap is genuine and addressable by agents."""

    def _format_execution_results(
        self, results: dict[int, list[ExecutionResult]]
    ) -> str:
        """Format execution results for prompts."""
        parts = []
        for step_num in sorted(results.keys()):
            for result in results[step_num]:
                parts.append(
                    f"---\nStep {step_num} | Agent: {result.agent}\n"
                    f"Question: {result.question}\n"
                    f"Response: {result.response}\n---"
                )
        return "\n".join(parts) if parts else "(No results)"


# === Unified Triage Routing ===
def select_triage_path(
    triage: TriagePlanOutput | TriageReplanOutput, target_ids: list[str]
) -> list[str]:
    """Select path after triage (handles both plan and replan outputs).

    target_ids order: [clarify_executor, reject_query, orchestrator, streaming_summary]
    """
    clarify_id, reject_id, orchestrator_id, streaming_id = target_ids

    if isinstance(triage, TriagePlanOutput):
        # Plan mode routing
        if triage.action == "clarify":
            return [clarify_id]
        elif triage.action == "reject":
            return [reject_id]
        else:  # action == "plan"
            return [orchestrator_id]
    else:
        # Replan mode routing (TriageReplanOutput)
        if triage.action == "retry" and triage.new_plan:
            return [orchestrator_id]
        elif triage.action == "clarify":
            return [clarify_id]
        else:  # action == "reject" or no valid plan
            return [streaming_id]


# === Reject Handler ===
@executor(id="reject_query")
async def reject_query(
    triage: TriagePlanOutput, ctx: WorkflowContext[Never, str]
) -> None:
    """Handle rejected queries."""
    await ctx.yield_output(
        f"I don't have knowledge about that topic. {triage.reject_reason}\n\n"
        "I can only help with:\n"
        "- ServiceNow operations (change requests, incidents)\n"
        "- Azure Data Factory pipeline monitoring\n"
        "- Service health checks (Databricks, Snowflake, Azure)"
    )


# === Clarify Executor ===
class ClarifyExecutor(Executor):
    """Executor for clarification requests."""

    def __init__(self, agent: ChatAgent, id: str = "clarify_executor"):
        super().__init__(id=id)
        self._agent = agent

    @handler
    async def handle_plan_clarify(
        self, triage: TriagePlanOutput, ctx: WorkflowContext[Never, str]
    ) -> None:
        """Generate clarification request from plan agent."""
        await self._generate_clarification(triage.reject_reason, ctx)

    @handler
    async def handle_replan_clarify(
        self, triage: TriageReplanOutput, ctx: WorkflowContext[Never, str]
    ) -> None:
        """Generate clarification request from replan agent."""
        await self._generate_clarification(triage.clarification_reason, ctx)

    async def _generate_clarification(
        self, reason: str, ctx: WorkflowContext[Never, str]
    ) -> None:
        """Generate clarification request with given reason."""
        original_query = await ctx.get_shared_state("original_query")
        prompt = f"""The user asked: "{original_query}"

This query is related to data operations but is unclear or ambiguous.
Reason: {reason}

Please provide a polite clarification request.

Output JSON with ClarifyOutput schema:
- clarification_request: str
- possible_interpretations: list[str]"""

        response = await self._agent.run(
            messages=[ChatMessage(Role.USER, text=prompt)]
        )

        output = ClarifyOutput.model_validate_json(response.text)

        # Format output for user
        interpretations = "\n".join(
            f"  - {interp}" for interp in output.possible_interpretations
        )
        message = f"{output.clarification_request}\n\nPossible interpretations:\n{interpretations}"

        await ctx.yield_output(message)


# === Dynamic Orchestrator ===
class DynamicOrchestrator(Executor):
    """Orchestrator that executes plans with step-based parallelism."""

    def __init__(self, agents: dict[str, ChatAgent], id: str = "orchestrator"):
        super().__init__(id=id)
        self._agents = agents

    @handler
    async def execute_plan(
        self, triage: TriagePlanOutput, ctx: WorkflowContext[ReviewRequest | StreamingRequest]
    ) -> None:
        """Execute the plan from plan mode triage (initial)."""
        all_results = await self._run_plan(triage.plan, {})

        # Store results
        await ctx.set_shared_state("execution_results", all_results)

        # Initial execution goes to review
        await ctx.send_message(ReviewRequest(execution_results=all_results))

    @handler
    async def execute_new_plan(
        self, triage: TriageReplanOutput, ctx: WorkflowContext[ReviewRequest | StreamingRequest]
    ) -> None:
        """Execute new plan from replan mode (retry)."""
        previous_results = await ctx.get_shared_state("execution_results") or {}

        # Execute new plan
        new_results = await self._run_plan(triage.new_plan, previous_results)

        # Merge with previous results (increment step numbers)
        max_step = max(previous_results.keys()) if previous_results else 0
        merged_results = dict(previous_results)
        for step_num, step_results in new_results.items():
            merged_results[max_step + step_num] = step_results

        # Store merged results
        await ctx.set_shared_state("execution_results", merged_results)

        # Retry execution goes directly to streaming (no review)
        await ctx.send_message(StreamingRequest(execution_results=merged_results))

    async def _run_plan(
        self,
        plan: list[PlanStep],
        existing_results: dict[int, list[ExecutionResult]],
    ) -> dict[int, list[ExecutionResult]]:
        """Run a plan with step-based parallelism."""
        all_results: dict[int, list[ExecutionResult]] = {}

        # Group tasks by step number
        steps_grouped: dict[int, list[PlanStep]] = defaultdict(list)
        for task in plan:
            steps_grouped[task.step].append(task)

        # Execute steps in order
        for step_num in sorted(steps_grouped.keys()):
            tasks = steps_grouped[step_num]

            # Build context from previous step (N-1)
            prev_step = step_num - 1
            context = ""
            prev_results = all_results.get(prev_step) or existing_results.get(prev_step)
            if prev_results:
                context_parts = []
                for result in prev_results:
                    context_parts.append(
                        f"---\nAgent: {result.agent}\n"
                        f"Question: {result.question}\n"
                        f"Response: {result.response}\n---"
                    )
                context = "Previous step results:\n" + "\n".join(context_parts)

            # Execute all tasks in this step in parallel
            step_results = await self._execute_step_parallel(tasks, context)
            all_results[step_num] = step_results

        return all_results

    async def _execute_step_parallel(
        self, tasks: list[PlanStep], context: str
    ) -> list[ExecutionResult]:
        """Execute all tasks in a step concurrently."""

        async def run_single_task(task: PlanStep) -> ExecutionResult:
            agent = self._agents[task.agent]

            # Build message with context if available
            message = task.question
            if context:
                message = f"{context}\n\nYour task: {task.question}"

            response = await agent.run(
                messages=[ChatMessage(Role.USER, text=message)]
            )

            return ExecutionResult(
                agent=task.agent,
                question=task.question,
                response=response.text,
            )

        # Execute ALL tasks in parallel
        results = await asyncio.gather(*[run_single_task(t) for t in tasks])
        return list(results)


# === Review Executor ===
class ReviewExecutor(Executor):
    """Executor for reviewing execution results."""

    def __init__(
        self,
        review_agent: ChatAgent,
        summary_agent: ChatAgent,
        id: str = "review_executor",
    ):
        super().__init__(id=id)
        self._review_agent = review_agent
        self._summary_agent = summary_agent
        self.output_response = True  # Enable streaming event detection

    @handler
    async def review(
        self, request: ReviewRequest, ctx: WorkflowContext[ReplanRequest, str]
    ) -> None:
        """Review execution results for completeness."""
        original_query = await ctx.get_shared_state("original_query")

        # Build review prompt
        results_str = self._format_results(request.execution_results)
        prompt = f"""## Review Request

## Original User Query
{original_query}

## Execution Results
{results_str}

## Instructions
Evaluate whether the execution results fully answer the user's query.
Output JSON with ReviewOutput schema:
- is_complete: bool
- missing_aspects: list[str] (if incomplete)
- suggested_approach: str (if incomplete)
- confidence: float (0.0 to 1.0)"""

        response = await self._review_agent.run(
            messages=[ChatMessage(Role.USER, text=prompt)]
        )

        output = ReviewOutput.model_validate_json(response.text)

        if output.is_complete:
            # Stream the final summary
            await self._stream_summary(request.execution_results, original_query, ctx)
        else:
            # Send to replan
            await ctx.send_message(
                ReplanRequest(
                    original_query=original_query,
                    previous_results=request.execution_results,
                    missing_aspects=output.missing_aspects,
                    suggested_approach=output.suggested_approach,
                )
            )

    async def _stream_summary(
        self,
        results: dict[int, list[ExecutionResult]],
        original_query: str,
        ctx: WorkflowContext,
    ) -> None:
        """Stream the final summary using summary agent."""
        results_str = self._format_results(results)
        prompt = f"""Answer the user's question based on the collected data.

## User's Question
{original_query}

## Collected Data
{results_str}

## Your Task
1. Start with a direct answer (1-2 sentences summary)
2. Include the detailed data - preserve all tables, lists, and specifics
3. Add insights or recommended actions if relevant"""

        # Stream the response using AgentRunUpdateEvent for SSE streaming
        # Also collect full text for workflow output
        full_response_parts: list[str] = []
        async for event in self._summary_agent.run_stream(
            messages=[ChatMessage(Role.USER, text=prompt)]
        ):
            if event.text:
                full_response_parts.append(event.text)
                await ctx.add_event(AgentRunUpdateEvent(self.id, event))

        # Emit WorkflowOutputEvent with the complete response
        full_response = "".join(full_response_parts)
        if full_response:
            await ctx.yield_output(full_response)

    def _format_results(
        self, results: dict[int, list[ExecutionResult]]
    ) -> str:
        """Format execution results for review."""
        parts = []
        for step_num in sorted(results.keys()):
            for result in results[step_num]:
                parts.append(
                    f"---\nStep {step_num} | Agent: {result.agent}\n"
                    f"Question: {result.question}\n"
                    f"Response:\n{result.response}\n---"
                )
        return "\n".join(parts) if parts else "(No results)"


# === Streaming Summary Executor (for retry path) ===
class StreamingSummaryExecutor(Executor):
    """Executor for streaming final output after retry."""

    def __init__(self, summary_agent: ChatAgent, id: str = "streaming_summary"):
        super().__init__(id=id)
        self._summary_agent = summary_agent
        self.output_response = True  # Enable streaming event detection

    @handler
    async def stream_output(
        self, request: StreamingRequest, ctx: WorkflowContext[Never, str]
    ) -> None:
        """Stream the final summary."""
        original_query = await ctx.get_shared_state("original_query")
        results_str = self._format_results(request.execution_results)

        prompt = f"""Answer the user's question based on the collected data.

## User's Question
{original_query}

## Collected Data
{results_str}

## Your Task
1. Start with a direct answer (1-2 sentences summary)
2. Include the detailed data - preserve all tables, lists, and specifics
3. Add insights or recommended actions if relevant"""

        # Stream the response using AgentRunUpdateEvent for SSE streaming
        # Also collect full text for workflow output
        full_response_parts: list[str] = []
        async for event in self._summary_agent.run_stream(
            messages=[ChatMessage(Role.USER, text=prompt)]
        ):
            if event.text:
                full_response_parts.append(event.text)
                await ctx.add_event(AgentRunUpdateEvent(self.id, event))

        # Emit WorkflowOutputEvent with the complete response
        full_response = "".join(full_response_parts)
        if full_response:
            await ctx.yield_output(full_response)

    @handler
    async def stream_existing(
        self, triage: TriageReplanOutput, ctx: WorkflowContext[Never, str]
    ) -> None:
        """Stream existing results when replan is rejected."""
        original_query = await ctx.get_shared_state("original_query")
        execution_results = await ctx.get_shared_state("execution_results") or {}
        results_str = self._format_results(execution_results)

        prompt = f"""Answer the user's question based on the collected data.

## User's Question
{original_query}

## Collected Data
{results_str}

## Your Task
1. Start with a direct answer (1-2 sentences summary)
2. Include the detailed data - preserve all tables, lists, and specifics
3. Add insights or recommended actions if relevant"""

        # Stream the response using AgentRunUpdateEvent for SSE streaming
        # Also collect full text for workflow output
        full_response_parts: list[str] = []
        async for event in self._summary_agent.run_stream(
            messages=[ChatMessage(Role.USER, text=prompt)]
        ):
            if event.text:
                full_response_parts.append(event.text)
                await ctx.add_event(AgentRunUpdateEvent(self.id, event))

        # Emit WorkflowOutputEvent with the complete response
        full_response = "".join(full_response_parts)
        if full_response:
            await ctx.yield_output(full_response)

    def _format_results(
        self, results: dict[int, list[ExecutionResult]]
    ) -> str:
        """Format execution results for summary."""
        parts = []
        for step_num in sorted(results.keys()):
            for result in results[step_num]:
                parts.append(
                    f"---\nAgent: {result.agent}\n"
                    f"Question: {result.question}\n"
                    f"Response:\n{result.response}\n---"
                )
        return "\n".join(parts) if parts else "(No results)"


# === Workflow Factory ===
def create_dynamic_workflow(
    registry: Optional[ModelRegistry] = None,
    workflow_model: Optional[ModelName] = None,
    agent_mapping: Optional[AgentModelMapping] = None,
):
    """Create the dynamic workflow with review loop.

    Args:
        registry: ModelRegistry for cloud mode, None for env settings (Mode 1)
        workflow_model: Model for all agents (required for Mode 2/3)
        agent_mapping: Per-agent model override (Mode 3)

    Mode 1: create_dynamic_workflow()
        - Uses env settings (for devui, local dev)

    Mode 2: create_dynamic_workflow(registry, "gpt-4.1-mini")
        - All agents use gpt-4.1-mini

    Mode 3: create_dynamic_workflow(registry, "gpt-4.1", AgentModelMapping(...))
        - Per-agent customization

    Raises:
        ValueError: If registry is provided but workflow_model is None
    """
    if registry is None:
        # Mode 1: env settings
        plan_agent = create_plan_agent()
        replan_agent = create_replan_agent()
        review_agent = create_review_agent()
        summary_agent = create_summary_agent()
        clarify_agent = create_clarify_agent()
        servicenow_agent = create_servicenow_agent()
        log_analytics_agent = create_log_analytics_agent()
        service_health_agent = create_service_health_agent()
    else:
        # Mode 2 & 3: registry with model resolution
        if workflow_model is None:
            raise ValueError("workflow_model is required when registry is provided")
        model_for = create_model_resolver(workflow_model, agent_mapping)
        plan_agent = create_plan_agent(registry, model_for("plan"))
        replan_agent = create_replan_agent(registry, model_for("replan"))
        review_agent = create_review_agent(registry, model_for("review"))
        summary_agent = create_summary_agent(registry, model_for("summary"))
        clarify_agent = create_clarify_agent(registry, model_for("clarify"))
        servicenow_agent = create_servicenow_agent(registry, model_for("servicenow"))
        log_analytics_agent = create_log_analytics_agent(registry, model_for("log_analytics"))
        service_health_agent = create_service_health_agent(registry, model_for("service_health"))

    # Create executors
    triage = TriageExecutor(plan_agent, replan_agent)
    clarify_executor = ClarifyExecutor(clarify_agent)
    orchestrator = DynamicOrchestrator(
        agents={
            "servicenow": servicenow_agent,
            "log_analytics": log_analytics_agent,
            "service_health": service_health_agent,
        }
    )
    review_executor = ReviewExecutor(review_agent, summary_agent)
    streaming_summary = StreamingSummaryExecutor(summary_agent)

    # Build workflow
    # max_iterations controls the maximum number of "super steps" (full graph traversals)
    # A retry path needs: store→triage→orchestrator→review→triage→orchestrator→streaming
    # Setting to 10 allows for reasonable retry loops while preventing infinite loops
    workflow = (
        WorkflowBuilder(
            name="Dynamic Ops Workflow",
            description="Dynamic multi-agent workflow with planning, execution, and review loop",
            max_iterations=10,
        )
        # Phase 1: Input → Triage (plan mode)
        .set_start_executor(store_query)
        .add_edge(store_query, triage)
        # Phase 2: Triage routing (unified for both plan and replan outputs)
        .add_multi_selection_edge_group(
            triage,
            [clarify_executor, reject_query, orchestrator, streaming_summary],
            selection_func=select_triage_path,
        )
        # Phase 3: Orchestrator → Review (for initial) or StreamingSummary (for retry)
        .add_edge(orchestrator, review_executor)
        .add_edge(orchestrator, streaming_summary)
        # Phase 4: Review → Triage (replan mode) if incomplete
        .add_edge(review_executor, triage)
        .build()
    )

    return workflow
