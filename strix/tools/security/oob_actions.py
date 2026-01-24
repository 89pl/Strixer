from typing import Any, Dict, List, Optional
import os
import logging
from strix.tools.registry import register_tool
from strix.tools.security.oob_manager import OOBManager

logger = logging.getLogger(__name__)

@register_tool
def oob_init(agent_state: Any) -> Dict[str, str]:
    """
    Initializes a new Out-of-Band (OOB) testing session.
    Returns the base OOB URL to use for payloads.
    """
    manager = OOBManager()
    try:
        session = manager.register()
        agent_state.oob_correlation_id = session["correlation_id"]
        agent_state.oob_secret_key = session["secret_key"]
        
        return {
            "success": "true",
            "oob_url": session["oob_url"],
            "message": "OOB session initialized. Use oob_get_url to generate payload-specific URLs."
        }
    except Exception as e:
        return {"success": "false", "error": str(e)}

@register_tool
def oob_get_url(agent_state: Any, identifier: Optional[str] = None) -> Dict[str, str]:
    """
    Generates a unique OOB URL for a specific payload or test case.
    Use 'identifier' to track which payload triggered which hit.
    """
    if not agent_state.oob_correlation_id:
        return {"success": "false", "error": "OOB session not initialized. Call oob_init first."}
    
    manager = OOBManager()
    server = manager.DEFAULT_SERVER
    url = manager.generate_payload_url(agent_state.oob_correlation_id, server, prefix=identifier)
    
    return {
        "success": "true",
        "url": url,
        "full_url": f"http://{url}",
        "identifier": identifier or "default"
    }

@register_tool
def oob_poll(agent_state: Any) -> Dict[str, Any]:
    """
    Polls the OOB server for any interactions (DNS, HTTP, etc.).
    Returns a list of interactions seen since last poll.
    """
    if not agent_state.oob_correlation_id or not agent_state.oob_secret_key:
        return {"success": "false", "error": "OOB session not initialized."}
    
    manager = OOBManager()
    try:
        interactions = manager.poll(agent_state.oob_correlation_id, agent_state.oob_secret_key)
        return {
            "success": "true",
            "interactions_count": len(interactions),
            "interactions": interactions
        }
    except Exception as e:
        return {"success": "false", "error": str(e)}
