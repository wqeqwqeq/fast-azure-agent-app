"""Utility modules for Azure OpenAI configuration.

NOTE: Settings have been moved to app.opsagent.model_registry.
This module re-exports for backward compatibility.
"""

from ..model_registry import (
    AzOpenAIEnvSettings,
    ModelDefinition,
    ModelName,
    ResolvedModelConfig,
)

__all__ = [
    "AzOpenAIEnvSettings",
    "ModelDefinition",
    "ModelName",
    "ResolvedModelConfig",
]
