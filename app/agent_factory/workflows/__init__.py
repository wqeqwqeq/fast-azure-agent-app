"""Workflows for Agent Factory.

This module provides dynamically configurable workflows that use
the AgentRegistry to load sub-agents at runtime.
"""

from .dynamic_workflow import create_dynamic_workflow

__all__ = ["create_dynamic_workflow"]
