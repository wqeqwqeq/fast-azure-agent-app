"""Dynamic Workflow for Agent Factory.

This workflow uses SubAgentRegistry to dynamically configure:
- Orchestration agents (with build_prompt/build_schema)
- Sub-agents (from subagent_config.py)
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional

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
from agent_framework._workflows._events import AgentRunUpdateEvent
from typing_extensions import Never

from ..agents.orchestration import (
    create_clarify_agent,
    create_plan_agent,
    create_replan_agent,
    create_review_agent,
    create_summary_agent,
)
from ..agents.orchestration.triage_agent import TriageAgentConfig
from ..model_registry import (
    DynamicAgentModelMapping,
    ModelName,
    ModelRegistry,
    create_dynamic_model_resolver,
)
from ..prompts.templates import REJECTION_MESSAGE_TEMPLATE
from ..schemas.dynamic import (
    create_clarify_output_schema,
    create_review_output_schema,
    create_triage_plan_output_schema,
    create_triage_replan_output_schema,
)
from ..subagent_registry import SubAgentRegistry, get_registry

from ..schemas.common import WorkflowInput


# === Internal Dataclasses ===
@dataclass
class ExecutionResult:
    agent: str
    question: str
    response: str


@dataclass
class PlanRequest:
    messages: list[ChatMessage]


@dataclass
class ReplanRequest:
    original_query: str
    previous_results: dict[int, list[ExecutionResult]]
    missing_aspects: list[str]
    suggested_approach: str


@dataclass
class ReviewRequest:
    execution_results: dict[int, list[ExecutionResult]]


@dataclass
class StreamingRequest:
    execution_results: dict[int, list[ExecutionResult]]


# === Input Processing ===
@executor(id="store_query")
async def store_query(input: WorkflowInput, ctx: WorkflowContext[PlanRequest]) -> None:
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
    await ctx.set_shared_state("is_retry", False)
    await ctx.send_message(PlanRequest(messages=chat_messages))


# === Triage Executor ===
class TriageExecutor(Executor):
    def __init__(
        self,
        plan_agent: ChatAgent,
        replan_agent: ChatAgent,
        sub_registry: SubAgentRegistry,
        id: str = "triage",
    ):
        super().__init__(id=id)
        self._plan_agent = plan_agent
        self._replan_agent = replan_agent
        self._registry = sub_registry
        self._TriagePlanOutput = create_triage_plan_output_schema(sub_registry.agent_keys)
        self._TriageReplanOutput = create_triage_replan_output_schema(sub_registry.agent_keys)

    @handler
    async def handle_plan(self, request: PlanRequest, ctx: WorkflowContext) -> None:
        prompt = self._build_plan_prompt(request.messages)
        response = await self._plan_agent.run(
            messages=[ChatMessage(Role.USER, text=prompt)]
        )
        output = self._TriagePlanOutput.model_validate_json(response.text)
        await ctx.set_shared_state("current_plan", output.plan)
        await ctx.send_message(output)

    @handler
    async def handle_replan(self, request: ReplanRequest, ctx: WorkflowContext) -> None:
        prompt = self._build_replan_prompt(request)
        response = await self._replan_agent.run(
            messages=[ChatMessage(Role.USER, text=prompt)]
        )
        output = self._TriageReplanOutput.model_validate_json(response.text)
        if output.action == "retry":
            await ctx.set_shared_state("is_retry", True)
        await ctx.send_message(output)

    def _build_plan_prompt(self, messages: list[ChatMessage]) -> str:
        history = "\n".join(f"[{msg.role.value}]: {msg.text}" for msg in messages)
        agents_list = ", ".join(self._registry.agent_keys)
        return f"""Analyze this conversation and create an execution plan.

## Conversation History
{history}

## Instructions
Output a JSON object with the following schema:
- action: "plan" | "clarify" | "reject"
- reject_reason: string (if clarify or reject)
- clarification_reason: string (if clarify)
- plan: list of {{step, agent, question}} where agent is one of: {agents_list}
- plan_reason: string

Remember: same step number = parallel, different step numbers = sequential."""

    def _build_replan_prompt(self, request: ReplanRequest) -> str:
        results_str = self._format_results(request.previous_results)
        agents_list = ", ".join(self._registry.agent_keys)
        return f"""The review agent found gaps in the response. Decide how to proceed.

## Original Query
{request.original_query}

## Previous Execution Results
{results_str}

## Review Feedback
- Missing aspects: {request.missing_aspects}
- Suggested approach: {request.suggested_approach}

## Instructions
Output a JSON object:
- action: "retry" | "clarify" | "complete"
- new_plan: list of {{step, agent, question}} (if retry) where agent is one of: {agents_list}
- completion_reason: string (if complete)
- clarification_reason: string (if clarify)"""

    def _format_results(self, results: dict[int, list[ExecutionResult]]) -> str:
        parts = []
        for step_num in sorted(results.keys()):
            for result in results[step_num]:
                parts.append(
                    f"---\nStep {step_num} | Agent: {result.agent}\n"
                    f"Question: {result.question}\nResponse: {result.response}\n---"
                )
        return "\n".join(parts) if parts else "(No results)"


# === Triage Path Selection ===
def create_triage_path_selector(agent_keys: list[str]):
    def select_triage_path(triage, target_ids: list[str]) -> list[str]:
        clarify_id, reject_id, orchestrator_id, streaming_id = target_ids
        if hasattr(triage, "plan") and hasattr(triage, "reject_reason"):
            if triage.action == "clarify":
                return [clarify_id]
            elif triage.action == "reject":
                return [reject_id]
            else:
                return [orchestrator_id]
        else:
            if triage.action == "retry" and triage.new_plan:
                return [orchestrator_id]
            elif triage.action == "clarify":
                return [clarify_id]
            else:
                return [streaming_id]
    return select_triage_path


# === Reject Executor Factory ===
def create_reject_executor(sub_registry: SubAgentRegistry):
    @executor(id="reject_query")
    async def reject_query(triage: Any, ctx: WorkflowContext[Never, str]) -> None:
        reject_reason = getattr(triage, "reject_reason", "Out of scope")
        message = REJECTION_MESSAGE_TEMPLATE.format(
            reject_reason=reject_reason,
            capabilities_summary=sub_registry.generate_capabilities_summary(),
        )
        await ctx.yield_output(message)
    return reject_query


# === Clarify Executor ===
class ClarifyExecutor(Executor):
    def __init__(self, agent: ChatAgent, id: str = "clarify_executor"):
        super().__init__(id=id)
        self._agent = agent
        self._ClarifyOutput = create_clarify_output_schema()

    @handler
    async def handle_clarify(self, triage: Any, ctx: WorkflowContext[Never, str]) -> None:
        # Handle both plan and replan clarify requests
        reason = getattr(triage, "clarification_reason", "") or getattr(triage, "reject_reason", "")
        await self._generate_clarification(reason, ctx)

    async def _generate_clarification(self, reason: str, ctx: WorkflowContext) -> None:
        original_query = await ctx.get_shared_state("original_query")
        prompt = f"""The user asked: "{original_query}"
This query is unclear or ambiguous. Reason: {reason}
Please provide a polite clarification request.
Output JSON: clarification_request (str), possible_interpretations (list[str])"""

        response = await self._agent.run(messages=[ChatMessage(Role.USER, text=prompt)])
        output = self._ClarifyOutput.model_validate_json(response.text)
        interpretations = "\n".join(f"  - {i}" for i in output.possible_interpretations)
        await ctx.yield_output(f"{output.clarification_request}\n\nPossible interpretations:\n{interpretations}")


# === Dynamic Orchestrator ===
class DynamicOrchestrator(Executor):
    def __init__(self, agents: dict[str, ChatAgent], id: str = "orchestrator"):
        super().__init__(id=id)
        self._agents = agents

    @handler
    async def handle_triage(self, triage: Any, ctx: WorkflowContext) -> None:
        # Handle both plan (from triage) and new_plan (from replan)
        # Note: Method renamed from 'execute' to avoid overriding Executor.execute()
        new_plan = getattr(triage, "new_plan", None)
        if new_plan:
            # Replan case: merge with previous results
            previous_results = await ctx.get_shared_state("execution_results") or {}
            new_results = await self._run_plan(new_plan, previous_results)
            max_step = max(previous_results.keys()) if previous_results else 0
            merged_results = dict(previous_results)
            for step_num, step_results in new_results.items():
                merged_results[max_step + step_num] = step_results
            await ctx.set_shared_state("execution_results", merged_results)
            await ctx.send_message(StreamingRequest(execution_results=merged_results))
        else:
            # Initial plan case
            plan = getattr(triage, "plan", [])
            all_results = await self._run_plan(plan, {})
            await ctx.set_shared_state("execution_results", all_results)
            await ctx.send_message(ReviewRequest(execution_results=all_results))

    async def _run_plan(self, plan: list, existing_results: dict) -> dict[int, list[ExecutionResult]]:
        all_results: dict[int, list[ExecutionResult]] = {}
        steps_grouped: dict[int, list] = defaultdict(list)
        for task in plan:
            steps_grouped[getattr(task, "step", 1)].append(task)

        for step_num in sorted(steps_grouped.keys()):
            tasks = steps_grouped[step_num]
            prev_step = step_num - 1
            context = ""
            prev_results = all_results.get(prev_step) or existing_results.get(prev_step)
            if prev_results:
                context_parts = [
                    f"---\nAgent: {r.agent}\nQuestion: {r.question}\nResponse: {r.response}\n---"
                    for r in prev_results
                ]
                context = "Previous step results:\n" + "\n".join(context_parts)

            step_results = await self._execute_step_parallel(tasks, context)
            all_results[step_num] = step_results
        return all_results

    async def _execute_step_parallel(self, tasks: list, context: str) -> list[ExecutionResult]:
        async def run_single(task) -> ExecutionResult:
            agent_key = getattr(task, "agent", "")
            question = getattr(task, "question", "")
            if agent_key not in self._agents:
                return ExecutionResult(agent_key, question, f"Error: Agent '{agent_key}' not found")
            agent = self._agents[agent_key]
            message = f"{context}\n\nYour task: {question}" if context else question
            response = await agent.run(messages=[ChatMessage(Role.USER, text=message)])
            return ExecutionResult(agent_key, question, response.text)

        results = await asyncio.gather(*[run_single(t) for t in tasks])
        return list(results)


# === Review Executor ===
class ReviewExecutor(Executor):
    def __init__(self, review_agent: ChatAgent, summary_agent: ChatAgent, id: str = "review_executor"):
        super().__init__(id=id)
        self._review_agent = review_agent
        self._summary_agent = summary_agent
        self._ReviewOutput = create_review_output_schema()
        self.output_response = True

    @handler
    async def review(self, request: ReviewRequest, ctx: WorkflowContext) -> None:
        original_query = await ctx.get_shared_state("original_query")
        results_str = self._format_results(request.execution_results)
        prompt = f"""## Original Query\n{original_query}\n\n## Execution Results\n{results_str}\n
Evaluate completeness. Output JSON: is_complete (bool), missing_aspects (list), suggested_approach (str), confidence (float)."""

        response = await self._review_agent.run(messages=[ChatMessage(Role.USER, text=prompt)])
        output = self._ReviewOutput.model_validate_json(response.text)

        if output.is_complete:
            await self._stream_summary(request.execution_results, original_query, ctx)
        else:
            await ctx.send_message(ReplanRequest(
                original_query=original_query,
                previous_results=request.execution_results,
                missing_aspects=output.missing_aspects,
                suggested_approach=output.suggested_approach,
            ))

    async def _stream_summary(self, results: dict, original_query: str, ctx: WorkflowContext) -> None:
        results_str = self._format_results(results)
        prompt = f"""Answer the user's question based on collected data.
## User's Question\n{original_query}\n\n## Collected Data\n{results_str}"""

        full_parts = []
        async for event in self._summary_agent.run_stream(messages=[ChatMessage(Role.USER, text=prompt)]):
            if event.text:
                full_parts.append(event.text)
                await ctx.add_event(AgentRunUpdateEvent(self.id, event))
        if full_parts:
            await ctx.yield_output("".join(full_parts))

    def _format_results(self, results: dict[int, list[ExecutionResult]]) -> str:
        parts = []
        for step_num in sorted(results.keys()):
            for r in results[step_num]:
                parts.append(f"---\nStep {step_num} | Agent: {r.agent}\nQuestion: {r.question}\nResponse:\n{r.response}\n---")
        return "\n".join(parts) if parts else "(No results)"


# === Streaming Summary Executor ===
class StreamingSummaryExecutor(Executor):
    def __init__(self, summary_agent: ChatAgent, id: str = "streaming_summary"):
        super().__init__(id=id)
        self._summary_agent = summary_agent
        self.output_response = True

    @handler
    async def stream_output(self, request: StreamingRequest, ctx: WorkflowContext[Never, str]) -> None:
        original_query = await ctx.get_shared_state("original_query")
        results_str = self._format_results(request.execution_results)
        await self._stream(original_query, results_str, ctx)

    @handler
    async def stream_existing(self, triage: Any, ctx: WorkflowContext[Never, str]) -> None:
        original_query = await ctx.get_shared_state("original_query")
        execution_results = await ctx.get_shared_state("execution_results") or {}
        results_str = self._format_results(execution_results)
        await self._stream(original_query, results_str, ctx)

    async def _stream(self, query: str, results_str: str, ctx: WorkflowContext) -> None:
        prompt = f"""Answer the user's question based on collected data.
## User's Question\n{query}\n\n## Collected Data\n{results_str}"""

        full_parts = []
        async for event in self._summary_agent.run_stream(messages=[ChatMessage(Role.USER, text=prompt)]):
            if event.text:
                full_parts.append(event.text)
                await ctx.add_event(AgentRunUpdateEvent(self.id, event))
        if full_parts:
            await ctx.yield_output("".join(full_parts))

    def _format_results(self, results: dict[int, list[ExecutionResult]]) -> str:
        parts = []
        for step_num in sorted(results.keys()):
            for r in results[step_num]:
                parts.append(f"---\nAgent: {r.agent}\nQuestion: {r.question}\nResponse:\n{r.response}\n---")
        return "\n".join(parts) if parts else "(No results)"


# === Workflow Factory ===
def create_dynamic_workflow(
    sub_registry: Optional[SubAgentRegistry] = None,
    model_registry: Optional[ModelRegistry] = None,
    workflow_model: Optional[ModelName] = None,
    agent_mapping: Optional[DynamicAgentModelMapping] = None,
):
    """Create the dynamic workflow with configurable sub-agents.

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

    # Create orchestration agents
    if model_registry is None:
        plan_agent = create_plan_agent(sub_registry)
        replan_agent = create_replan_agent(sub_registry)
        review_agent = create_review_agent(sub_registry)
        summary_agent = create_summary_agent(sub_registry)
        clarify_agent = create_clarify_agent(sub_registry)
        sub_agents = sub_registry.create_all_agents()
    else:
        if workflow_model is None:
            raise ValueError("workflow_model required when model_registry provided")
        model_for = create_dynamic_model_resolver(workflow_model, agent_mapping)
        plan_agent = create_plan_agent(sub_registry, model_registry, model_for("plan"))
        replan_agent = create_replan_agent(sub_registry, model_registry, model_for("replan"))
        review_agent = create_review_agent(sub_registry, model_registry, model_for("review"))
        summary_agent = create_summary_agent(sub_registry, model_registry, model_for("summary"))
        clarify_agent = create_clarify_agent(sub_registry, model_registry, model_for("clarify"))
        sub_agents = sub_registry.create_all_agents(model_registry, model_for)

    # Create executors
    triage = TriageExecutor(plan_agent, replan_agent, sub_registry)
    clarify_executor = ClarifyExecutor(clarify_agent)
    orchestrator = DynamicOrchestrator(agents=sub_agents)
    review_executor = ReviewExecutor(review_agent, summary_agent)
    streaming_summary = StreamingSummaryExecutor(summary_agent)
    reject_query = create_reject_executor(sub_registry)

    select_triage_path = create_triage_path_selector(sub_registry.agent_keys)

    # Build workflow
    workflow = (
        WorkflowBuilder(
            name=f"{sub_registry.domain_name} Workflow",
            description=f"Dynamic workflow for {sub_registry.domain_description}",
            max_iterations=10,
        )
        .set_start_executor(store_query)
        .add_edge(store_query, triage)
        .add_multi_selection_edge_group(
            triage,
            [clarify_executor, reject_query, orchestrator, streaming_summary],
            selection_func=select_triage_path,
        )
        .add_edge(orchestrator, review_executor)
        .add_edge(orchestrator, streaming_summary)
        .add_edge(review_executor, triage)
        .build()
    )

    return workflow
