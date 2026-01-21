from typing import Any

from strix.agents.base_agent import BaseAgent
from strix.llm.llm import LLMConfig
from strix.tools.security.waf_evasion import WAFEvasionEngine


class WAFEvasionAgent(BaseAgent):
    """
    A specialized agent for bypassing Web Application Firewalls (WAFs).
    It initializes with a specialized system prompt and context to drive the LLM
    towards polymorphic payload generation.
    """

    def __init__(self, config: dict[str, Any]):
        # Ensure LLM is configured for high creativity/reasoning
        if "llm_config" not in config:
            config["llm_config"] = LLMConfig(
                model="gpt-4o",
                temperature=0.8, # Higher temperature for creative evasion
            )
        
        # Ensure web_search is available for 0-day research
        if "tools" in config and isinstance(config["tools"], list):
            if "web_search" not in config["tools"]:
                config["tools"].append("web_search")
                # Also add search_web alias just in case
                config["tools"].append("search_web")
        
        super().__init__(config)
        self.engine = WAFEvasionEngine()

    # Redundant _inject_security_personality removed as we use system.j2

