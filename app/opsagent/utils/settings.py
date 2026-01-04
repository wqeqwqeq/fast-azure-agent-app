import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
load_dotenv()

# Singleton cache
_settings_instance: Optional["AzureOpenAISettings"] = None


def get_azure_openai_settings() -> "AzureOpenAISettings":
    """Get cached AzureOpenAISettings instance (singleton)."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = AzureOpenAISettings()
    return _settings_instance


class AzureOpenAISettings(BaseSettings):
    """Azure OpenAI configuration with Key Vault support."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_api_key: str = ""  # Allow empty, will be loaded from Key Vault
    azure_openai_endpoint: str = "https://stanleyai.cognitiveservices.azure.com/"
    azure_openai_deployment_name: str

    def __init__(self, **data):
        super().__init__(**data)
        if not self.azure_openai_api_key:
            self._load_from_keyvault()

    def _load_from_keyvault(self):
        """Load azure_openai_api_key from Key Vault using RESOURCE_PREFIX."""
        resource_prefix = os.getenv("RESOURCE_PREFIX")
        if resource_prefix:
            vault_name = f"{resource_prefix.replace('-', '')}kv"
            from .keyvault import AKV
            akv = AKV(vault_name)
            secret_value = akv.get_secret("AZURE-OPENAI-API-KEY")
            if secret_value:
                object.__setattr__(self, "azure_openai_api_key", secret_value)
            else:
                raise ValueError(f"Failed to load AZURE_OPENAI_API_KEY from {vault_name}")
        else:
            raise ValueError("AZURE_OPENAI_API_KEY not set and RESOURCE_PREFIX not configured")
