"""LLM module for Strix - Direct HTTP-based LLM client with CLIProxyAPI support."""

from strix.llm.direct_api import (
    DirectAPIClient,
    DirectAPIError,
    DirectAPIResponse,
    get_direct_api_client,
    is_direct_api_mode,
)

from .config import LLMConfig
from .llm import LLM, LLMRequestFailedError, LLMResponse, RequestStats


__all__ = [
    "LLM",
    "LLMConfig",
    "LLMRequestFailedError",
    "LLMResponse",
    "RequestStats",
    "DirectAPIClient",
    "DirectAPIError",
    "DirectAPIResponse",
    "get_direct_api_client",
    "is_direct_api_mode",
]

# Conditional litellm initialization
try:
    if not is_direct_api_mode():
        import litellm
        litellm._logging._disable_debugging()
except ImportError:
    # LiteLLM not available, using direct API mode
    pass
