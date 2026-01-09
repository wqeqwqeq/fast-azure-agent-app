"""Azure OpenAI settings configuration."""

import os
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

# Singleton cache
_settings_instance: Optional["AzureOpenAISettings"] = None


class AzureOpenAISettings(BaseSettings):
    """Azure OpenAI configuration.

    API key should be provided via:
    1. Environment variable AZURE_OPENAI_API_KEY
    2. Calling initialize_azure_openai_settings() with pre-loaded secret from Key Vault
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = "https://stanleyai.cognitiveservices.azure.com/"
    azure_openai_deployment_name: str = ""


def initialize_azure_openai_settings(api_key: str) -> "AzureOpenAISettings":
    """Initialize AzureOpenAISettings singleton with the provided API key.

    Call this from lifespan after loading secrets from Key Vault.

    Args:
        api_key: Azure OpenAI API key from Key Vault

    Returns:
        Initialized AzureOpenAISettings instance
    """
    global _settings_instance
    _settings_instance = AzureOpenAISettings(azure_openai_api_key=api_key)
    return _settings_instance


def get_azure_openai_settings() -> "AzureOpenAISettings":
    """Get cached AzureOpenAISettings instance (singleton).

    Raises:
        RuntimeError: If settings not initialized and no env var set
    """
    global _settings_instance
    if _settings_instance is None:
        # Try to create from env var
        _settings_instance = AzureOpenAISettings()
        if not _settings_instance.azure_openai_api_key:
            raise RuntimeError(
                "AzureOpenAISettings not initialized. "
                "Either set AZURE_OPENAI_API_KEY env var or call "
                "initialize_azure_openai_settings() from lifespan."
            )
    return _settings_instance
