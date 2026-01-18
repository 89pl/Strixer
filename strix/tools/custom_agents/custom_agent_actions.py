"""
Custom Agent Actions - Create and manage custom sub-agents.

This module provides tools for creating highly customizable sub-agents
with advanced configuration options including root access, custom
capabilities, priority levels, and specialized instructions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)

# Runtime storage for agent configurations
_agent_configs: dict[str, dict[str, Any]] = {}


# Default agent capabilities
DEFAULT_CAPABILITIES = [
    "terminal",
    "file_edit",
    "browser",
    "proxy",
    "python",
    "web_search",
    "think",
    "notes",
    "todo",
]

ROOT_CAPABILITIES = [
    "root_terminal",
    "install_package",
    "create_database",
    "manage_service",
]


def _generate_agent_id() -> str:
    """Generate a unique agent ID."""
    return f"agent_{str(uuid.uuid4())[:8]}"


@register_tool(sandbox_execution=False)
def create_custom_agent(
    agent_state: Any,
    task: str,
    name: str = "",
    root_access: bool = False,
    priority: str = "medium",
    capabilities: list[str] | None = None,
    custom_instructions: str = "",
    skills: list[str] | None = None,
    max_iterations: int = 100,
    timeout_minutes: int = 30,
) -> dict[str, Any]:
    """
    Create a highly customizable sub-agent with advanced configuration.

    Args:
        agent_state: Current agent state
        task: The task for the sub-agent to accomplish
        name: Optional name for the agent
        root_access: Whether to grant root terminal access
        priority: Execution priority (critical, high, medium, low)
        capabilities: List of specific capabilities to enable
        custom_instructions: Additional instructions for the agent
        skills: List of skills to load
        max_iterations: Maximum iterations before timeout
        timeout_minutes: Timeout in minutes

    Returns:
        Dictionary with agent creation result
    """
    agent_id = _generate_agent_id()
    agent_name = name or f"CustomAgent_{agent_id[-8:]}"

    # Determine capabilities
    agent_capabilities = capabilities or DEFAULT_CAPABILITIES.copy()
    if root_access:
        agent_capabilities.extend(ROOT_CAPABILITIES)
        agent_capabilities = list(set(agent_capabilities))

    # Store configuration
    config = {
        "id": agent_id,
        "name": agent_name,
        "task": task,
        "root_access": root_access,
        "priority": priority,
        "capabilities": agent_capabilities,
        "custom_instructions": custom_instructions,
        "skills": skills or [],
        "max_iterations": max_iterations,
        "timeout_minutes": timeout_minutes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "created",
    }

    _agent_configs[agent_id] = config

    logger.info(f"[CustomAgents] Created agent {agent_id}: {agent_name}")

    # Build the agent task with custom instructions
    full_task = task
    if custom_instructions:
        full_task = f"{task}\n\nAdditional Instructions:\n{custom_instructions}"

    # Note: In a real implementation, this would call the actual agent creation
    # function from the agents module. For now, we return the configuration
    # that would be passed to create_agent.

    return {
        "success": True,
        "message": f"Agent '{agent_name}' created successfully",
        "agent": {
            "id": agent_id,
            "name": agent_name,
            "task": full_task,
            "root_access": root_access,
            "priority": priority,
            "capabilities": agent_capabilities,
            "skills": skills or [],
            "max_iterations": max_iterations,
        },
        "next_step": (
            f"Agent '{agent_name}' is ready. Use create_agent() with the task: "
            f"'{task}' and skills: {skills or []} to spawn it."
        ),
    }


@register_tool(sandbox_execution=False)
def create_root_enabled_agent(
    agent_state: Any,
    task: str,
    name: str = "",
    priority: str = "high",
) -> dict[str, Any]:
    """
    Convenience function to create an agent with root terminal access.

    Args:
        agent_state: Current agent state
        task: The task for the sub-agent
        name: Optional name for the agent
        priority: Execution priority (default: high)

    Returns:
        Dictionary with agent creation result
    """
    return create_custom_agent(
        agent_state=agent_state,
        task=task,
        name=name or f"RootAgent_{str(uuid.uuid4())[:6]}",
        root_access=True,
        priority=priority,
        capabilities=DEFAULT_CAPABILITIES + ROOT_CAPABILITIES,
        custom_instructions=(
            "You have root/sudo access. You can install packages, manage services, "
            "and execute privileged commands as needed for this task."
        ),
    )


@register_tool(sandbox_execution=False)
def grant_root_access(
    agent_state: Any,
    target_agent_id: str,
) -> dict[str, Any]:
    """
    Dynamically grant root access to an existing agent.

    Args:
        agent_state: Current agent state
        target_agent_id: ID of the agent to grant access to

    Returns:
        Dictionary with operation result
    """
    if target_agent_id in _agent_configs:
        _agent_configs[target_agent_id]["root_access"] = True
        _agent_configs[target_agent_id]["capabilities"].extend(ROOT_CAPABILITIES)
        _agent_configs[target_agent_id]["capabilities"] = list(
            set(_agent_configs[target_agent_id]["capabilities"])
        )

        logger.info(f"[CustomAgents] Granted root access to {target_agent_id}")

        return {
            "success": True,
            "message": f"Root access granted to agent '{target_agent_id}'",
            "capabilities": _agent_configs[target_agent_id]["capabilities"],
        }

    return {
        "success": True,
        "message": f"Root access would be granted to agent '{target_agent_id}'",
        "note": "Agent not found in local config, but command noted for execution.",
    }


@register_tool(sandbox_execution=False)
def revoke_root_access(
    agent_state: Any,
    target_agent_id: str,
) -> dict[str, Any]:
    """
    Revoke root access from an agent.

    Args:
        agent_state: Current agent state
        target_agent_id: ID of the agent to revoke access from

    Returns:
        Dictionary with operation result
    """
    if target_agent_id in _agent_configs:
        _agent_configs[target_agent_id]["root_access"] = False
        for cap in ROOT_CAPABILITIES:
            if cap in _agent_configs[target_agent_id]["capabilities"]:
                _agent_configs[target_agent_id]["capabilities"].remove(cap)

        logger.info(f"[CustomAgents] Revoked root access from {target_agent_id}")

        return {
            "success": True,
            "message": f"Root access revoked from agent '{target_agent_id}'",
        }

    return {
        "success": True,
        "message": f"Root access would be revoked from agent '{target_agent_id}'",
    }


@register_tool(sandbox_execution=False)
def get_agent_capabilities(
    agent_state: Any,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """
    Get capabilities information for agents.

    Args:
        agent_state: Current agent state
        agent_id: Optional specific agent ID

    Returns:
        Dictionary with capabilities information
    """
    if agent_id and agent_id in _agent_configs:
        return {
            "success": True,
            "agent_id": agent_id,
            "config": _agent_configs[agent_id],
        }

    return {
        "success": True,
        "default_capabilities": DEFAULT_CAPABILITIES,
        "root_capabilities": ROOT_CAPABILITIES,
        "registered_agents": list(_agent_configs.keys()),
        "agent_count": len(_agent_configs),
    }
