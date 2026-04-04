"""
HashiCorp Vault client wrapper.
All secrets are read from Vault — never from environment variables directly in prod.
For local dev, falls back to .env.local via python-dotenv.
"""

import os
import hvac
from functools import lru_cache
from typing import Optional


class VaultClient:
    def __init__(self):
        self._client: Optional[hvac.Client] = None
        self._env = os.getenv("APP_ENV", "local")

    def _connect(self) -> hvac.Client:
        if self._client and self._client.is_authenticated():
            return self._client

        vault_addr = os.getenv("VAULT_ADDR", "http://vault:8200")
        vault_token = os.getenv("VAULT_TOKEN")  # injected by K8s Vault Agent sidecar

        self._client = hvac.Client(url=vault_addr, token=vault_token)

        if not self._client.is_authenticated():
            raise RuntimeError("Vault authentication failed. Check VAULT_TOKEN and VAULT_ADDR.")

        return self._client

    def get_secret(self, path: str, key: str = "value") -> str:
        """
        Reads a secret from Vault KV v2.

        Usage:
            vault.get_secret("github/app-private-key")
            vault.get_secret("jira/api-token")
            vault.get_secret("anthropic/api-key")
        """
        if self._env == "local":
            # In local dev, secrets come from .env.local
            env_key = path.replace("/", "_").replace("-", "_").upper()
            value = os.getenv(env_key)
            if value is None:
                raise EnvironmentError(
                    f"Local secret not found. Add '{env_key}' to your .env.local file."
                )
            return value

        client = self._connect()
        mount_point, secret_path = path.split("/", 1)

        response = client.secrets.kv.v2.read_secret_version(
            mount_point=mount_point,
            path=secret_path,
        )
        data = response["data"]["data"]

        if key not in data:
            raise KeyError(f"Key '{key}' not found in Vault secret at '{path}'")

        return data[key]


@lru_cache(maxsize=1)
def get_vault_client() -> VaultClient:
    return VaultClient()
