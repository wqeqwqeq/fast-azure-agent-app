"""Utility modules for Azure OpenAI configuration.

NOTE: Settings have been moved to app.opsagent.settings.
This module re-exports for backward compatibility.
"""

from ..settings import (
    AzOpenAIEnvSettings,
    ModelConfig,
    ResolvedModelConfig,
    resolve_model_config,
)

__all__ = [
    "AzOpenAIEnvSettings",
    "ModelConfig",
    "ResolvedModelConfig",
    "resolve_model_config",
]
