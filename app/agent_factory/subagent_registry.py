"""Sub-Agent Registry.

Simple registry that manages sub-agent configurations.
Reads from subagent_config.py (AI generated).
"""

import importlib
from functools import lru_cache
from typing import TYPE_CHECKING, Callable, Optional

from .schemas.config import SubAgentConfig
from .subagent_config import DOMAIN_DESCRIPTION, DOMAIN_NAME, SUB_AGENTS

if TYPE_CHECKING:
    from agent_framework import ChatAgent

    from .model_registry import ModelRegistry


class SubAgentRegistry:
    """Registry for sub-agent configurations.

    This is a simplified registry that only manages sub-agents.
    Orchestration agents handle their own prompt/schema building.
    """

    def __init__(
        self,
        sub_agents: list[SubAgentConfig] = SUB_AGENTS,
        domain_name: str = DOMAIN_NAME,
        domain_description: str = DOMAIN_DESCRIPTION,
    ):
        self._sub_agents = sub_agents
        self._domain_name = domain_name
        self._domain_description = domain_description
        self._agent_modules: dict[str, object] = {}

    # =========================================================================
    # Domain Info
    # =========================================================================

    @property
    def domain_name(self) -> str:
        """Get the domain name."""
        return self._domain_name

    @property
    def domain_description(self) -> str:
        """Get the domain description."""
        return self._domain_description

    # =========================================================================
    # Sub-Agent Info
    # =========================================================================

    @property
    def agent_keys(self) -> list[str]:
        """Get list of all sub-agent keys."""
        return [a.key for a in self._sub_agents]

    @property
    def sub_agents(self) -> list[SubAgentConfig]:
        """Get all sub-agent configurations."""
        return self._sub_agents

    def get_agent(self, key: str) -> Optional[SubAgentConfig]:
        """Get sub-agent config by key."""
        for agent in self._sub_agents:
            if agent.key == key:
                return agent
        return None

    def has_agents(self) -> bool:
        """Check if any sub-agents are configured."""
        return len(self._sub_agents) > 0

    # =========================================================================
    # Description Generation (for orchestration agents to use)
    # =========================================================================

    def generate_descriptions(self) -> str:
        """Generate markdown descriptions of all agents.

        Used by orchestration agents to build their prompts.

        Returns:
            Markdown formatted agent list with capabilities
        """
        if not self._sub_agents:
            return "No specialized agents available."

        lines = []
        for agent in self._sub_agents:
            lines.append(f"- **{agent.key}** ({agent.name}): {agent.description}")
            if agent.capabilities:
                for cap in agent.capabilities:
                    lines.append(f"  - {cap}")
        return "\n".join(lines)

    def generate_descriptions_with_tools(self) -> str:
        """Generate detailed descriptions including tools.

        Returns:
            Markdown formatted agent list with tools
        """
        if not self._sub_agents:
            return "No specialized agents available."

        lines = []
        for agent in self._sub_agents:
            lines.append(f"- **{agent.key}** ({agent.name}): {agent.description}")
            if agent.tools:
                tool_names = ", ".join(t.name for t in agent.tools)
                lines.append(f"  - Tools: {tool_names}")
            if agent.capabilities:
                lines.append(f"  - Use for: {', '.join(agent.capabilities)}")
            lines.append("")
        return "\n".join(lines)

    def generate_capabilities_summary(self) -> str:
        """Generate bullet list of capabilities by agent.

        Returns:
            Markdown bullet list
        """
        if not self._sub_agents:
            return "- General assistance"

        lines = []
        for agent in self._sub_agents:
            if agent.capabilities:
                cap_list = ", ".join(agent.capabilities)
                lines.append(f"- **{agent.name}**: {cap_list}")
        return "\n".join(lines) if lines else "- General assistance"

    # =========================================================================
    # Agent Creation
    # =========================================================================

    def _load_agent_module(self, key: str) -> Optional[object]:
        """Dynamically load an agent module."""
        if key in self._agent_modules:
            return self._agent_modules[key]

        try:
            module_path = f"app.agent_factory.agents.sub_agents.{key}_agent"
            module = importlib.import_module(module_path)
            self._agent_modules[key] = module
            return module
        except ImportError:
            return None

    def create_agent(
        self,
        key: str,
        model_registry: Optional["ModelRegistry"] = None,
        model_name: Optional[str] = None,
    ) -> Optional["ChatAgent"]:
        """Create a sub-agent instance by key."""
        module = self._load_agent_module(key)
        if module is None:
            return None

        factory_func_name = f"create_{key}_agent"
        if not hasattr(module, factory_func_name):
            return None

        factory_func: Callable = getattr(module, factory_func_name)
        return factory_func(registry=model_registry, model_name=model_name)

    def create_all_agents(
        self,
        model_registry: Optional["ModelRegistry"] = None,
        model_resolver: Optional[Callable[[str], str]] = None,
    ) -> dict[str, "ChatAgent"]:
        """Create all registered sub-agents."""
        agents = {}
        for key in self.agent_keys:
            model_name = model_resolver(key) if model_resolver else None
            agent = self.create_agent(key, model_registry, model_name)
            if agent is not None:
                agents[key] = agent
        return agents


# =============================================================================
# Global Registry
# =============================================================================


@lru_cache(maxsize=1)
def get_registry() -> SubAgentRegistry:
    """Get the singleton registry instance."""
    return SubAgentRegistry()


def reload_registry() -> SubAgentRegistry:
    """Reload the registry (after /onboard generates new config)."""
    get_registry.cache_clear()

    # Reimport subagent_config to pick up changes
    from . import subagent_config

    importlib.reload(subagent_config)

    return get_registry()
