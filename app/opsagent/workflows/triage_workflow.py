"""Triage Workflow with fan-out/fan-in pattern for multi-agent execution."""

from dataclasses import dataclass
from typing import Optional

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
from typing_extensions import Never

from ..agents.log_analytics_agent import create_log_analytics_agent
from ..agents.service_health_agent import create_service_health_agent
from ..agents.servicenow_agent import create_servicenow_agent
from ..agents.triage_agent import create_triage_agent
from ..model_registry import AgentModelMapping, ModelName, ModelRegistry, create_model_resolver
from ..schemas.common import WorkflowInput
from ..schemas.triage import TriageOutput


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
    # Handle both input modes: query (DevUI) or messages (Flask)
    if input.messages:
        # Flask mode: convert MessageData to ChatMessage
        chat_messages = [
            ChatMessage(
                Role.USER if msg.role == "user" else Role.ASSISTANT,
                text=msg.text,
            )
            for msg in input.messages
        ]
    else:
        # DevUI mode: create single user message from query
        chat_messages = [ChatMessage(Role.USER, text=input.query)]

    # Store the full conversation history for reference
    await ctx.set_shared_state("conversation_history", chat_messages)

    # Extract latest user query for original_query
    latest_query = ""
    for msg in reversed(chat_messages):
        if msg.role == Role.USER:
            latest_query = msg.text
            break
    await ctx.set_shared_state("original_query", latest_query)

    # Send full history to triage agent
    await ctx.send_message(
        AgentExecutorRequest(messages=chat_messages, should_respond=True)
    )


@executor(id="parse_triage_output")
async def parse_triage_output(
    response: AgentExecutorResponse, ctx: WorkflowContext[TriageOutput]
) -> None:
    """Parse triage agent JSON output into TriageOutput for routing."""
    triage = TriageOutput.model_validate_json(response.agent_run_response.text)

    # Store tasks in shared state for agent bridges to access
    await ctx.set_shared_state("tasks", triage.tasks)

    await ctx.send_message(triage)


@executor(id="reject_query")
async def reject_query(triage: TriageOutput, ctx: WorkflowContext[Never, str]) -> None:
    """Handle rejected queries."""
    await ctx.yield_output(
        f"I don't have knowledge about that topic. {triage.reject_reason}\n\n"
        "I can only help with:\n"
        "- ServiceNow operations (change requests, incidents)\n"
        "- Azure Data Factory pipeline monitoring\n"
        "- Service health checks (Databricks, Snowflake, Azure)"
    )


# === Dispatcher for Fan-Out ===
class DispatchToAgents(Executor):
    """Dispatches triage result to all agent executors for parallel processing."""

    def __init__(self, id: str = "dispatch_to_agents"):
        super().__init__(id=id)

    @handler
    async def dispatch(
        self, triage: TriageOutput, ctx: WorkflowContext[TriageOutput]
    ) -> None:
        # Only dispatch if not rejected and has tasks
        if not triage.should_reject and triage.tasks:
            # Send triage result to all agents (fan-out edges will route it)
            await ctx.send_message(triage)


# === Filtered Agent Executor ===
# Custom executor that filters tasks and invokes the wrapped agent directly
class FilteredAgentExecutor(Executor):
    """Agent executor that filters tasks and invokes the wrapped agent."""

    def __init__(self, agent: ChatAgent, agent_key: str, id: str):
        super().__init__(id=id)
        self._agent = agent
        self._agent_key = agent_key  # "servicenow", "log_analytics", "service_health"

    @handler
    async def handle(
        self, triage: TriageOutput, ctx: WorkflowContext[AgentResponse]
    ) -> None:
        # Collect all tasks for this agent
        questions = [
            task.question for task in triage.tasks if task.agent == self._agent_key
        ]

        if not questions:
            # No tasks for this agent - send empty response for fan-in
            await ctx.send_message(
                AgentResponse(
                    executor_id=self.id,
                    text="",  # Empty response, will be filtered in aggregator
                )
            )
            return

        # Combine questions if multiple
        combined = (
            "\n".join(f"- {q}" for q in questions)
            if len(questions) > 1
            else questions[0]
        )

        # Invoke the agent (ChatAgent.run() returns AgentRunResponse)
        response = await self._agent.run(
            messages=[ChatMessage(Role.USER, text=combined)]
        )

        # Send response for fan-in aggregation
        await ctx.send_message(
            AgentResponse(
                executor_id=self.id,
                text=response.text,
            )
        )


# === Aggregator for Fan-In ===
class AggregateResponses(Executor):
    """Aggregate responses from specialized agents."""

    def __init__(self, id: str = "aggregate_responses"):
        super().__init__(id=id)

    @handler
    async def aggregate(
        self, results: list[AgentResponse], ctx: WorkflowContext[Never, str]
    ) -> None:
        # Build consolidated response, filtering out empty responses
        sections = []
        for r in results:
            if r.text:  # Only include non-empty responses
                agent_name = (
                    r.executor_id.replace("_executor", "").replace("_", " ").title()
                )
                sections.append(f"## {agent_name}\n{r.text}")

        consolidated = "\n\n---\n\n".join(sections)
        await ctx.yield_output(consolidated)


# === Selection Function for Dispatch vs Reject ===
def select_dispatch_or_reject(triage: TriageOutput, target_ids: list[str]) -> list[str]:
    """Select dispatcher or reject based on triage result.

    target_ids order: [dispatch_to_agents, reject_query]
    """
    dispatch_id, reject_id = target_ids

    if triage.should_reject or not triage.tasks:
        return [reject_id]

    return [dispatch_id]


# === Workflow Factory ===
def create_triage_workflow(
    registry: Optional[ModelRegistry] = None,
    workflow_model: Optional[ModelName] = None,
    agent_mapping: Optional[AgentModelMapping] = None,
):
    """Create the triage workflow with conditional fan-out.

    Args:
        registry: ModelRegistry for cloud mode, None for env settings (Mode 1)
        workflow_model: Model for all agents (required for Mode 2/3)
        agent_mapping: Per-agent model override (Mode 3)

    Mode 1: create_triage_workflow()
        - Uses env settings (for devui, local dev)

    Mode 2: create_triage_workflow(registry, "gpt-4.1-mini")
        - All agents use gpt-4.1-mini

    Mode 3: create_triage_workflow(registry, "gpt-4.1", AgentModelMapping(...))
        - Per-agent customization

    Raises:
        ValueError: If registry is provided but workflow_model is None
    """
    if registry is None:
        # Mode 1: env settings
        triage = create_triage_agent()
        servicenow = create_servicenow_agent()
        log_analytics = create_log_analytics_agent()
        service_health = create_service_health_agent()
    else:
        # Mode 2 & 3: registry with model resolution
        if workflow_model is None:
            raise ValueError("workflow_model is required when registry is provided")
        model_for = create_model_resolver(workflow_model, agent_mapping)
        triage = create_triage_agent(registry, model_for("triage"))
        servicenow = create_servicenow_agent(registry, model_for("servicenow"))
        log_analytics = create_log_analytics_agent(registry, model_for("log_analytics"))
        service_health = create_service_health_agent(registry, model_for("service_health"))

    # Triage uses standard AgentExecutor (for structured output)
    triage_executor = AgentExecutor(triage, id="triage_agent")

    # Dispatcher routes to all agents
    dispatcher = DispatchToAgents()

    # Wrap domain agents with FilteredAgentExecutor (each checks if it has tasks)
    servicenow_executor = FilteredAgentExecutor(
        servicenow, "servicenow", id="servicenow_executor"
    )
    log_analytics_executor = FilteredAgentExecutor(
        log_analytics, "log_analytics", id="log_analytics_executor"
    )
    service_health_executor = FilteredAgentExecutor(
        service_health, "service_health", id="service_health_executor"
    )

    aggregator = AggregateResponses()

    # Build workflow
    workflow = (
        WorkflowBuilder(
            name='Data Ops Triage Workflow',
            description='Routes data ops queries to specialized agents for ServiceNow, Log Analytics, and Service Health.'
        )
        .set_start_executor(store_query)
        .add_edge(store_query, triage_executor)
        .add_edge(triage_executor, parse_triage_output)
        # Route to dispatcher OR reject
        .add_multi_selection_edge_group(
            parse_triage_output,
            [dispatcher, reject_query],
            selection_func=select_dispatch_or_reject,
        )
        # Fan-out from dispatcher to ALL agents (they filter internally)
        .add_fan_out_edges(
            dispatcher,
            [servicenow_executor, log_analytics_executor, service_health_executor],
        )
        # Fan-in from all agents to aggregator
        .add_fan_in_edges(
            [servicenow_executor, log_analytics_executor, service_health_executor],
            aggregator,
        )
        .build()
    )

    return workflow
