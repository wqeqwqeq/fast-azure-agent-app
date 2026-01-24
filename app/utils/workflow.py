"""Workflow creation utilities.

Handles dynamic workflow and input creation based on configuration.
"""

from typing import Any, Optional, Tuple


def create_workflow_and_input(
    use_demo_opsagent: bool,
    react_mode: bool,
    registry: Any,
    workflow_model: str,
    agent_level_llm_overwrite: Any,
    user_content: str,
) -> Tuple[Any, Any]:
    """Create the appropriate workflow and input based on configuration.

    This function ensures that the WorkflowInput type matches the workflow's
    expected input type by importing from the same module.

    Args:
        use_demo_opsagent: If True, use opsagent workflows; if False, use agent_factory
        react_mode: If True, use dynamic workflow; if False, use triage workflow
        registry: Model registry for cloud deployment
        workflow_model: Model to use for all agents
        agent_level_llm_overwrite: Per-agent model overrides
        user_content: User message content for workflow input

    Returns:
        Tuple of (workflow, input_data) with matching types
    """
    if use_demo_opsagent:
        # Use opsagent workflows (demo application)
        from ..opsagent.schemas.common import MessageData, WorkflowInput
        from ..opsagent.workflows.dynamic_workflow import (
            create_dynamic_workflow as opsagent_dynamic,
        )
        from ..opsagent.workflows.triage_workflow import (
            create_triage_workflow as opsagent_triage,
        )

        if react_mode:
            workflow = opsagent_dynamic(registry, workflow_model, agent_level_llm_overwrite)
        else:
            workflow = opsagent_triage(registry, workflow_model, agent_level_llm_overwrite)
    else:
        # Use agent_factory workflows (configurable application)
        from ..agent_factory.schemas.common import MessageData, WorkflowInput
        from ..agent_factory.subagent_registry import get_registry
        from ..agent_factory.workflows.dynamic_workflow import (
            create_dynamic_workflow as factory_dynamic,
        )
        from ..agent_factory.workflows.triage_workflow import (
            create_triage_workflow as factory_triage,
        )

        sub_registry = get_registry()

        if react_mode:
            workflow = factory_dynamic(
                sub_registry=sub_registry,
                model_registry=registry,
                workflow_model=workflow_model,
                agent_mapping=agent_level_llm_overwrite,
            )
        else:
            workflow = factory_triage(
                sub_registry=sub_registry,
                model_registry=registry,
                workflow_model=workflow_model,
                agent_mapping=agent_level_llm_overwrite,
            )

    # Create input data with the correct types (same import scope)
    message_data = [MessageData(role="user", text=user_content)]
    input_data = WorkflowInput(messages=message_data)

    return workflow, input_data
