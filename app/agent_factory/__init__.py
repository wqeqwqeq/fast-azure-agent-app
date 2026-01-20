"""Agent Factory - Schema-driven agent generation system.

Architecture:
- subagent_config.py: AI-generated sub-agent configurations (by /onboard skill)
- subagent_registry.py: Simple registry for sub-agents
- agents/orchestration/*.py: Framework code with build_prompt/build_schema methods
- workflows/dynamic_workflow.py: Connects everything together

Usage:
    from app.agent_factory.subagent_registry import get_registry
    from app.agent_factory.workflows import create_dynamic_workflow

    registry = get_registry()
    workflow = create_dynamic_workflow(registry)
"""

from .subagent_registry import SubAgentRegistry, get_registry, reload_registry

__all__ = ["SubAgentRegistry", "get_registry", "reload_registry"]
