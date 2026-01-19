"""LLM module for Strix."""

# Original LLM classes (litellm-based)
from strix.llm.config import LLMConfig
from strix.llm.llm import LLM, LLMRequestFailedError, LLMResponse, RequestStats

# HTTP-based LLM client (for direct CLIProxyAPI usage)
from strix.llm.http_client import (
    LLMClient,
    chat,
    get_llm_client,
    stream_chat,
)

__all__ = [
    # Core LLM classes
    "LLM",
    "LLMConfig",
    "LLMRequestFailedError",
    "LLMResponse",
    "RequestStats",
    # HTTP client
    "LLMClient",
    "chat",
    "get_llm_client",
    "stream_chat",
]
