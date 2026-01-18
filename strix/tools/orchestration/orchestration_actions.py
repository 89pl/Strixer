"""
Advanced Multi-Agent Orchestration - Task management and coordination.

This module provides significantly improved coordination capabilities:
- Task Management: Priority queue with dependency resolution
- Workload Management: Capacity control and load balancing
- Team Management: Organize agents into functional teams
- Advanced Coordination: Broadcast messaging and sync points
- Workflow Automation: Multi-step workflow execution
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)

# Runtime storage
_tasks: dict[str, dict[str, Any]] = {}
_workflows: dict[str, dict[str, Any]] = {}
_teams: dict[str, dict[str, Any]] = {}
_agent_capacities: dict[str, dict[str, Any]] = {}
_sync_points: dict[str, dict[str, Any]] = {}
_messages: list[dict[str, Any]] = []

# Task statuses
TASK_STATUSES = ["pending", "assigned", "in_progress", "completed", "failed", "blocked"]
PRIORITY_LEVELS = ["critical", "high", "medium", "low"]


def _generate_id(prefix: str) -> str:
    """Generate a unique ID with prefix."""
    return f"{prefix}_{str(uuid.uuid4())[:8]}"


@register_tool(sandbox_execution=False)
def create_task(
    agent_state: Any,
    title: str,
    description: str,
    priority: str = "medium",
    depends_on: list[str] | None = None,
    assigned_to: str | None = None,
    tags: list[str] | None = None,
    estimated_minutes: int = 30,
) -> dict[str, Any]:
    """
    Create a new task in the orchestration system.

    Args:
        agent_state: Current agent state
        title: Task title
        description: Task description
        priority: Priority level (critical, high, medium, low)
        depends_on: List of task IDs this task depends on
        assigned_to: Agent ID to assign to
        tags: Tags for categorization
        estimated_minutes: Estimated time to complete

    Returns:
        Dictionary with created task
    """
    if priority not in PRIORITY_LEVELS:
        return {"success": False, "error": f"Invalid priority. Must be: {PRIORITY_LEVELS}"}

    task_id = _generate_id("task")
    now = datetime.now(timezone.utc).isoformat()

    task = {
        "id": task_id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": "pending",
        "depends_on": depends_on or [],
        "assigned_to": assigned_to,
        "tags": tags or [],
        "estimated_minutes": estimated_minutes,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "completed_at": None,
        "result": None,
    }

    # Check for circular dependencies
    if depends_on:
        for dep_id in depends_on:
            if dep_id in _tasks:
                dep_task = _tasks[dep_id]
                if task_id in dep_task.get("depends_on", []):
                    return {"success": False, "error": f"Circular dependency detected with {dep_id}"}

    _tasks[task_id] = task

    if assigned_to:
        task["status"] = "assigned"

    logger.info(f"[Orchestration] Created task {task_id}: {title}")

    return {
        "success": True,
        "message": f"Task '{title}' created",
        "task_id": task_id,
        "task": task,
    }


@register_tool(sandbox_execution=False)
def assign_task(
    agent_state: Any,
    task_id: str,
    agent_id: str,
    force: bool = False,
) -> dict[str, Any]:
    """
    Assign a task to an agent with load balancing consideration.

    Args:
        agent_state: Current agent state
        task_id: ID of task to assign
        agent_id: ID of agent to assign to
        force: Force assignment even if agent is at capacity

    Returns:
        Dictionary with assignment result
    """
    if task_id not in _tasks:
        return {"success": False, "error": f"Task '{task_id}' not found"}

    task = _tasks[task_id]

    # Check dependencies
    for dep_id in task.get("depends_on", []):
        if dep_id in _tasks and _tasks[dep_id]["status"] != "completed":
            return {
                "success": False,
                "error": f"Dependency '{dep_id}' not completed",
                "blocking_task": _tasks[dep_id],
            }

    # Check agent capacity
    if agent_id in _agent_capacities and not force:
        capacity = _agent_capacities[agent_id]
        current_tasks = sum(
            1 for t in _tasks.values()
            if t.get("assigned_to") == agent_id and t["status"] in ["assigned", "in_progress"]
        )
        if current_tasks >= capacity.get("max_concurrent", 5):
            return {
                "success": False,
                "error": f"Agent '{agent_id}' is at capacity ({current_tasks} tasks)",
                "suggestion": "Use force=True to override or assign to another agent",
            }

    task["assigned_to"] = agent_id
    task["status"] = "assigned"
    task["updated_at"] = datetime.now(timezone.utc).isoformat()

    return {
        "success": True,
        "message": f"Task '{task_id}' assigned to '{agent_id}'",
        "task": task,
    }


@register_tool(sandbox_execution=False)
def complete_task(
    agent_state: Any,
    task_id: str,
    result: str = "",
    status: str = "completed",
) -> dict[str, Any]:
    """
    Mark a task as completed or failed.

    Args:
        agent_state: Current agent state
        task_id: ID of task to complete
        result: Result/output of the task
        status: Final status (completed or failed)

    Returns:
        Dictionary with completion result
    """
    if task_id not in _tasks:
        return {"success": False, "error": f"Task '{task_id}' not found"}

    task = _tasks[task_id]
    now = datetime.now(timezone.utc).isoformat()

    task["status"] = status
    task["result"] = result
    task["completed_at"] = now
    task["updated_at"] = now

    # Check if this unblocks other tasks
    unblocked = []
    for other_id, other_task in _tasks.items():
        if task_id in other_task.get("depends_on", []):
            all_deps_done = all(
                _tasks.get(dep, {}).get("status") == "completed"
                for dep in other_task["depends_on"]
            )
            if all_deps_done and other_task["status"] == "pending":
                unblocked.append(other_id)

    return {
        "success": True,
        "message": f"Task '{task_id}' marked as {status}",
        "task": task,
        "unblocked_tasks": unblocked,
    }


@register_tool(sandbox_execution=False)
def create_workflow(
    agent_state: Any,
    name: str,
    description: str = "",
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Create a multi-step workflow with dependencies.

    Args:
        agent_state: Current agent state
        name: Workflow name
        description: Workflow description
        steps: List of workflow steps, each with:
            - name: Step name
            - task_template: Task description
            - depends_on: List of step names this depends on (optional)

    Returns:
        Dictionary with created workflow
    """
    workflow_id = _generate_id("wf")
    now = datetime.now(timezone.utc).isoformat()

    workflow = {
        "id": workflow_id,
        "name": name,
        "description": description,
        "steps": steps or [],
        "status": "created",
        "created_at": now,
        "executed_at": None,
        "task_ids": {},
    }

    _workflows[workflow_id] = workflow

    return {
        "success": True,
        "message": f"Workflow '{name}' created",
        "workflow_id": workflow_id,
        "workflow": workflow,
    }


@register_tool(sandbox_execution=False)
def execute_workflow(
    agent_state: Any,
    workflow_id: str,
    auto_assign: bool = True,
) -> dict[str, Any]:
    """
    Execute a workflow by creating tasks for each step.

    Args:
        agent_state: Current agent state
        workflow_id: ID of workflow to execute
        auto_assign: Automatically assign tasks

    Returns:
        Dictionary with execution result
    """
    if workflow_id not in _workflows:
        return {"success": False, "error": f"Workflow '{workflow_id}' not found"}

    workflow = _workflows[workflow_id]
    workflow["status"] = "executing"
    workflow["executed_at"] = datetime.now(timezone.utc).isoformat()

    # Create tasks for each step
    step_to_task: dict[str, str] = {}
    created_tasks = []

    for step in workflow["steps"]:
        step_name = step["name"]
        task_template = step.get("task_template", step_name)

        # Resolve dependencies to task IDs
        depends_on = []
        for dep_name in step.get("depends_on", []):
            if dep_name in step_to_task:
                depends_on.append(step_to_task[dep_name])

        result = create_task(
            agent_state=agent_state,
            title=f"[{workflow['name']}] {step_name}",
            description=task_template,
            priority=step.get("priority", "medium"),
            depends_on=depends_on,
            tags=["workflow", workflow_id],
        )

        if result["success"]:
            task_id = result["task_id"]
            step_to_task[step_name] = task_id
            created_tasks.append(task_id)

    workflow["task_ids"] = step_to_task

    return {
        "success": True,
        "message": f"Workflow '{workflow['name']}' execution started",
        "workflow": workflow,
        "created_tasks": created_tasks,
    }


@register_tool(sandbox_execution=False)
def create_agent_team(
    agent_state: Any,
    name: str,
    initial_members: list[str] | None = None,
    description: str = "",
) -> dict[str, Any]:
    """
    Create a team of agents for coordinated work.

    Args:
        agent_state: Current agent state
        name: Team name
        initial_members: List of agent IDs
        description: Team description

    Returns:
        Dictionary with created team
    """
    team_id = _generate_id("team")
    now = datetime.now(timezone.utc).isoformat()

    team = {
        "id": team_id,
        "name": name,
        "description": description,
        "members": [],
        "roles": {},
        "created_at": now,
    }

    for member in (initial_members or []):
        team["members"].append(member)
        team["roles"][member] = "member"

    _teams[team_id] = team

    return {
        "success": True,
        "message": f"Team '{name}' created",
        "team_id": team_id,
        "team": team,
    }


@register_tool(sandbox_execution=False)
def broadcast_message(
    agent_state: Any,
    message: str,
    target_agents: list[str] | None = None,
    team_id: str | None = None,
    priority: str = "medium",
) -> dict[str, Any]:
    """
    Broadcast a message to agents or teams.

    Args:
        agent_state: Current agent state
        message: Message to broadcast
        target_agents: Specific agent IDs to message
        team_id: Team to message
        priority: Message priority

    Returns:
        Dictionary with broadcast result
    """
    msg_id = _generate_id("msg")
    now = datetime.now(timezone.utc).isoformat()

    recipients = []
    if target_agents:
        recipients.extend(target_agents)
    if team_id and team_id in _teams:
        recipients.extend(_teams[team_id]["members"])

    recipients = list(set(recipients))

    msg = {
        "id": msg_id,
        "message": message,
        "priority": priority,
        "recipients": recipients,
        "team_id": team_id,
        "sent_at": now,
    }

    _messages.append(msg)

    return {
        "success": True,
        "message_id": msg_id,
        "recipients_count": len(recipients),
        "broadcast": msg,
    }


@register_tool(sandbox_execution=False)
def get_orchestration_dashboard(
    agent_state: Any,
) -> dict[str, Any]:
    """Get a comprehensive view of the orchestration state."""
    # Task statistics
    task_stats = {status: 0 for status in TASK_STATUSES}
    for task in _tasks.values():
        task_stats[task["status"]] = task_stats.get(task["status"], 0) + 1

    # Priority breakdown
    priority_stats = {p: 0 for p in PRIORITY_LEVELS}
    for task in _tasks.values():
        if task["status"] not in ["completed", "failed"]:
            priority_stats[task["priority"]] = priority_stats.get(task["priority"], 0) + 1

    # Agent workloads
    agent_workloads = {}
    for task in _tasks.values():
        agent = task.get("assigned_to")
        if agent and task["status"] in ["assigned", "in_progress"]:
            agent_workloads[agent] = agent_workloads.get(agent, 0) + 1

    return {
        "success": True,
        "dashboard": {
            "tasks": {
                "total": len(_tasks),
                "by_status": task_stats,
                "by_priority": priority_stats,
            },
            "workflows": {
                "total": len(_workflows),
                "active": sum(1 for w in _workflows.values() if w["status"] == "executing"),
            },
            "teams": {
                "total": len(_teams),
                "total_members": sum(len(t["members"]) for t in _teams.values()),
            },
            "agent_workloads": agent_workloads,
            "pending_messages": len([m for m in _messages]),
            "sync_points": len(_sync_points),
        },
    }


@register_tool(sandbox_execution=False)
def set_agent_capacity(
    agent_state: Any,
    agent_id: str,
    max_concurrent: int = 5,
) -> dict[str, Any]:
    """
    Set the maximum concurrent tasks for an agent.

    Args:
        agent_state: Current agent state
        agent_id: Agent ID
        max_concurrent: Maximum concurrent tasks (1-20)

    Returns:
        Dictionary with capacity settings
    """
    if not 1 <= max_concurrent <= 20:
        return {"success": False, "error": "max_concurrent must be between 1 and 20"}

    _agent_capacities[agent_id] = {
        "max_concurrent": max_concurrent,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "success": True,
        "message": f"Agent '{agent_id}' capacity set to {max_concurrent}",
        "capacity": _agent_capacities[agent_id],
    }


@register_tool(sandbox_execution=False)
def create_sync_point(
    agent_state: Any,
    name: str,
    required_agents: list[str],
    description: str = "",
) -> dict[str, Any]:
    """
    Create a synchronization point for multi-agent coordination.

    Args:
        agent_state: Current agent state
        name: Sync point name
        required_agents: List of agent IDs that must check in
        description: Description of the sync point

    Returns:
        Dictionary with sync point
    """
    sync_id = _generate_id("sync")
    now = datetime.now(timezone.utc).isoformat()

    sync = {
        "id": sync_id,
        "name": name,
        "description": description,
        "required_agents": required_agents,
        "checked_in": [],
        "status": "waiting",
        "created_at": now,
    }

    _sync_points[sync_id] = sync

    return {
        "success": True,
        "message": f"Sync point '{name}' created",
        "sync_id": sync_id,
        "sync_point": sync,
        "waiting_for": required_agents,
    }
