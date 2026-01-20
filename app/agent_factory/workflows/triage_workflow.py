"""Triage Workflow for Agent Factory.

This workflow uses SubAgentRegistry to dynamically configure:
- Triage agent for routing
- Sub-agents for task execution
- Fan-out/fan-in pattern for parallel execution
"""

from dataclasses import dataclass
from typing import Any, Optional

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatAgent,
    ChatMessage,
    Executor,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
)
from agent_framework._workflows._events import AgentRunUpdateEvent
from typing_extensions import Never

from ..agents.orchestration import create_summary_agent, create_triage_agent
from ..model_registry import (
    DynamicAgentModelMapping,
    ModelName,
    ModelRegistry,
    create_dynamic_model_resolver,
)
from ..prompts.templates import REJECTION_MESSAGE_TEMPLATE
from ..schemas.common import WorkflowInput
from ..schemas.dynamic import create_triage_output_schema
from ..subagent_registry import SubAgentRegistry, get_registry


# === Custom Response for Fan-In ===
@dataclass
class AgentResponse:
    """Response from a filtered agent executor for fan-in aggregation."""

    executor_id: str
    text: str


# === Executors ===


@executor(id="store_query")
async def store_query(
    input: WorkflowInput, ctx: WorkflowContext[AgentExecutorRequest]
) -> None:
    """Store conversation history and send to triage agent."""
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

    await ctx.set_shared_state("conversation_history", chat_messages)

    latest_query = ""
    for msg in reversed(chat_messages):
        if msg.role == Role.USER:
            latest_query = msg.text
            break
    await ctx.set_shared_state("original_query", latest_query)

    await ctx.send_message(
        AgentExecutorRequest(messages=chat_messages, should_respond=True)
    )


# === Parse Triage Output ===
def create_parse_triage_executor(triage_output_schema):
    """Create triage output parser with dynamic schema."""

    @executor(id="parse_triage_output")
    async def parse_triage_output(
        response: AgentExecutorResponse, ctx: WorkflowContext
    ) -> None:
        """Parse triage agent JSON output for routing."""
        triage = triage_output_schema.model_validate_json(response.agent_run_response.text)
        await ctx.set_shared_state("tasks", triage.tasks)
        await ctx.send_message(triage)

    return parse_triage_output


# === Reject Executor Factory ===
def create_reject_executor(sub_registry: SubAgentRegistry):
    """Create reject query executor with dynamic capabilities."""

    @executor(id="reject_query")
    async def reject_query(triage: Any, ctx: WorkflowContext[Never, str]) -> None:
        """Handle rejected queries."""
        reject_reason = getattr(triage, "reject_reason", "Out of scope")
        message = REJECTION_MESSAGE_TEMPLATE.format(
            reject_reason=reject_reason,
            capabilities_summary=sub_registry.generate_capabilities_summary(),
        )
        await ctx.yield_output(message)

    return reject_query


# === Dispatcher for Fan-Out ===
class DispatchToAgents(Executor):
    """Dispatches triage result to all agent executors for parallel processing."""

    def __init__(self, id: str = "dispatch_to_agents"):
        super().__init__(id=id)

    @handler
    async def dispatch(self, triage: Any, ctx: WorkflowContext) -> None:
        """Only dispatch if not rejected and has tasks."""
        should_reject = getattr(triage, "should_reject", False)
        tasks = getattr(triage, "tasks", [])
        if not should_reject and tasks:
            await ctx.send_message(triage)


# === Filtered Agent Executor ===
class FilteredAgentExecutor(Executor):
    """Agent executor that filters tasks and invokes the wrapped agent."""

    def __init__(self, agent: ChatAgent, agent_key: str, id: str):
        super().__init__(id=id)
        self._agent = agent
        self._agent_key = agent_key

    @handler
    async def handle_triage(self, triage: Any, ctx: WorkflowContext[AgentResponse]) -> None:
        """Filter tasks for this agent and execute."""
        tasks = getattr(triage, "tasks", [])
        questions = [
            getattr(task, "question", "") for task in tasks
            if getattr(task, "agent", "") == self._agent_key
        ]

        if not questions:
            await ctx.send_message(
                AgentResponse(executor_id=self.id, text="")
            )
            return

        combined = (
            "\n".join(f"- {q}" for q in questions)
            if len(questions) > 1
            else questions[0]
        )

        response = await self._agent.run(
            messages=[ChatMessage(Role.USER, text=combined)]
        )

        await ctx.send_message(
            AgentResponse(executor_id=self.id, text=response.text)
        )


# === Aggregator for Fan-In ===
class AggregateResponses(Executor):
    """Aggregate responses from specialized agents and send to summary agent."""

    def __init__(self, id: str = "aggregate_responses"):
        super().__init__(id=id)

    @handler
    async def aggregate(
        self, results: list[AgentResponse], ctx: WorkflowContext[str]
    ) -> None:
        """Build consolidated response, filtering out empty responses."""
        sections = []
        for r in results:
            if r.text:
                agent_name = (
                    r.executor_id.replace("_executor", "").replace("_", " ").title()
                )
                sections.append(f"## {agent_name}\n{r.text}")

        consolidated = "\n\n---\n\n".join(sections)
        await ctx.send_message(consolidated)


# === Streaming Summary Executor ===
class StreamingSummaryExecutor(Executor):
    """Streams final summary from the summary agent."""

    def __init__(self, summary_agent: ChatAgent, id: str = "streaming_summary"):
        super().__init__(id=id)
        self._summary_agent = summary_agent
        self.output_response = True

    @handler
    async def stream_summary(self, consolidated: str, ctx: WorkflowContext[Never, str]) -> None:
        """Stream the final summary response."""
        original_query = await ctx.get_shared_state("original_query")
        prompt = f"""Answer the user's question based on collected data.

## User's Question
{original_query}

## Collected Data
{consolidated}"""

        full_parts = []
        async for event in self._summary_agent.run_stream(
            messages=[ChatMessage(Role.USER, text=prompt)]
        ):
            if event.text:
                full_parts.append(event.text)
                await ctx.add_event(AgentRunUpdateEvent(self.id, event))
        if full_parts:
            await ctx.yield_output("".join(full_parts))


# === Selection Function for Dispatch vs Reject ===
def select_dispatch_or_reject(triage: Any, target_ids: list[str]) -> list[str]:
    """Select dispatcher or reject based on triage result.

    target_ids order: [dispatch_to_agents, reject_query]
    """
    dispatch_id, reject_id = target_ids

    should_reject = getattr(triage, "should_reject", False)
    tasks = getattr(triage, "tasks", [])

    if should_reject or not tasks:
        return [reject_id]

    return [dispatch_id]


# === Workflow Factory ===
def create_triage_workflow(
    sub_registry: Optional[SubAgentRegistry] = None,
    model_registry: Optional[ModelRegistry] = None,
    workflow_model: Optional[ModelName] = None,
    agent_mapping: Optional[DynamicAgentModelMapping] = None,
):
    """Create the triage workflow with dynamic sub-agents.

    Args:
        sub_registry: SubAgentRegistry (defaults to global registry)
        model_registry: ModelRegistry for cloud mode
        workflow_model: Model for all agents (required if model_registry provided)
        agent_mapping: Per-agent model overrides

    Returns:
        Configured Workflow instance
    """
    if sub_registry is None:
        sub_registry = get_registry()

    if not sub_registry.has_agents():
        raise ValueError("No sub-agents configured. Run /onboard to create your application.")

    # Create dynamic triage output schema
    TriageOutput = create_triage_output_schema(sub_registry.agent_keys)

    # Create agents
    if model_registry is None:
        triage_agent = create_triage_agent(sub_registry)
        summary_agent = create_summary_agent(sub_registry)
        sub_agents = sub_registry.create_all_agents()
    else:
        if workflow_model is None:
            raise ValueError("workflow_model required when model_registry provided")
        model_for = create_dynamic_model_resolver(workflow_model, agent_mapping)
        triage_agent = create_triage_agent(sub_registry, model_registry, model_for("triage"))
        summary_agent = create_summary_agent(sub_registry, model_registry, model_for("summary"))
        sub_agents = sub_registry.create_all_agents(model_registry, model_for)

    # Create executors
    triage_executor = AgentExecutor(triage_agent, id="triage_agent")
    parse_triage = create_parse_triage_executor(TriageOutput)
    dispatcher = DispatchToAgents()
    reject_query = create_reject_executor(sub_registry)

    # Create FilteredAgentExecutor for each sub-agent
    agent_executors = [
        FilteredAgentExecutor(agent, key, id=f"{key}_executor")
        for key, agent in sub_agents.items()
    ]

    aggregator = AggregateResponses()
    streaming_summary = StreamingSummaryExecutor(summary_agent)

    # Build workflow
    workflow = (
        WorkflowBuilder(
            name=f"{sub_registry.domain_name} Triage Workflow",
            description=f"Routes queries to {sub_registry.domain_description}",
            max_iterations=10,
        )
        .set_start_executor(store_query)
        .add_edge(store_query, triage_executor)
        .add_edge(triage_executor, parse_triage)
        .add_multi_selection_edge_group(
            parse_triage,
            [dispatcher, reject_query],
            selection_func=select_dispatch_or_reject,
        )
        .add_fan_out_edges(dispatcher, agent_executors)
        .add_fan_in_edges(agent_executors, aggregator)
        .add_edge(aggregator, streaming_summary)
        .build()
    )

    return workflow
