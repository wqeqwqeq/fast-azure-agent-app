"""Sub-agents for Agent Factory.

This directory contains dynamically generated sub-agents created by the /onboard skill.
Each sub-agent handles a specific domain capability (e.g., leave management, payroll, etc.).

Sub-agents are created with this structure:
- {key}_agent.py - Agent definition with create_{key}_agent() factory
- tools/{key}_tools.py - Tool functions for the agent
"""
