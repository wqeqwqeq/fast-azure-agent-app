"""Azure Key Vault utility for secret management."""

import os
import logging
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

logger = logging.getLogger(__name__)


class AKV:
    """Azure Key Vault client with pre-loaded secrets.

    All secrets are loaded at startup into memory. No TTL - secrets persist
    for the lifetime of the application.

    Secret rotation should be handled via deployment slot swap:
    1. Deploy new instance to staging slot
    2. Rotate secret in Key Vault
    3. Restart staging slot to fetch new secret
    4. Swap slots for zero-downtime rotation

    Uses DefaultAzureCredential for authentication:
    - Local: Azure CLI credentials
    - Production: Managed Identity
    """

    def __init__(self, vault_name: Optional[str] = None):
        """Initialize Key Vault client.

        Args:
            vault_name: Key Vault name. Defaults to AZURE_KEYVAULT_NAME env var.
        """
        self.vault_name = vault_name or os.getenv("AZURE_KEYVAULT_NAME")
        if not self.vault_name:
            raise ValueError("vault_name required or set AZURE_KEYVAULT_NAME")

        self.vault_url = f"https://{self.vault_name}.vault.azure.net/"
        self._credential = DefaultAzureCredential()
        self._client = SecretClient(vault_url=self.vault_url, credential=self._credential)
        self._secrets: dict[str, str] = {}

    def load_secrets(self, names: list[str]) -> None:
        """Pre-load all secrets at startup.

        Fails fast if any secret is missing or has no value.

        Args:
            names: List of secret names to load

        Raises:
            ValueError: If any secret is not found or has no value
        """
        for name in names:
            try:
                secret = self._client.get_secret(name)
                if secret.value is None:
                    raise ValueError(f"Secret '{name}' has no value")
                self._secrets[name] = secret.value
                logger.info(f"Loaded secret: {name}")
            except Exception as e:
                raise ValueError(f"Failed to load secret '{name}': {e}") from e

    def get_secret(self, name: str) -> str:
        """Get a pre-loaded secret by name.

        Args:
            name: Secret name

        Returns:
            Secret value

        Raises:
            KeyError: If secret was not pre-loaded
        """
        if name not in self._secrets:
            raise KeyError(
                f"Secret '{name}' not pre-loaded. "
                f"Add it to REQUIRED_SECRETS in lifespan."
            )
        return self._secrets[name]
