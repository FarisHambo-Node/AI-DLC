"""
LLM provider abstraction.
All agents use this factory — swap models centrally without touching agent code.
"""

from enum import Enum
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from shared.tools.vault_tool import VaultClient


class LLMProfile(str, Enum):
    # Use for: code generation, PR review, test writing, ticket parsing
    SONNET = "sonnet"

    # Use for: high-frequency cheap tasks (feedback-agent, log parsing)
    HAIKU = "haiku"

    # Use for: fallback or CI log analysis
    GPT4O = "gpt4o"


_MODEL_MAP = {
    LLMProfile.SONNET: ("anthropic", "claude-3-5-sonnet-20241022"),
    LLMProfile.HAIKU:  ("anthropic", "claude-3-haiku-20240307"),
    LLMProfile.GPT4O:  ("openai",    "gpt-4o"),
}

_cache: dict[LLMProfile, BaseChatModel] = {}


def get_llm(profile: LLMProfile = LLMProfile.SONNET, temperature: float = 0.0) -> BaseChatModel:
    """
    Returns a cached LLM instance for the given profile.
    Credentials are pulled from Vault at first call.
    """
    if profile in _cache:
        return _cache[profile]

    vault = VaultClient()
    provider, model_name = _MODEL_MAP[profile]

    if provider == "anthropic":
        api_key = vault.get_secret("anthropic/api-key")
        llm = ChatAnthropic(model=model_name, api_key=api_key, temperature=temperature, max_tokens=8192)

    elif provider == "openai":
        api_key = vault.get_secret("openai/api-key")
        llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=temperature)

    else:
        raise ValueError(f"Unknown provider: {provider}")

    _cache[profile] = llm
    return llm
