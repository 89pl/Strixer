"""
StrixDB Target Tracking System - Comprehensive Target Management

This module provides advanced target tracking capabilities for the AI agent.
It stores comprehensive information about each target scanned, enabling 
intelligent session continuity across multiple scan sessions.

KEY FEATURES:
- Comprehensive target profiles with all discovered data
- Session management for scan continuity
- Progress tracking to avoid redundant work
- Finding history with full details
- Technology stack tracking
- Endpoint/path discovery tracking
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import requests

from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)


def _get_strixdb_config() -> dict[str, str]:
    """Get StrixDB configuration."""
    from strix.tools.strixdb.strixdb_actions import _get_strixdb_config as get_config
    return get_config()


def _get_headers(token: str) -> dict[str, str]:
    """Get headers for GitHub API requests."""
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _sanitize_target_slug(target: str) -> str:
    """Create a safe directory-friendly slug from a target identifier."""
    target = re.sub(r'^https?://', '', target)
    target = target.split('/')[0]
    target = re.sub(r':\d+$', '', target)
    slug = re.sub(r'[^\w\-.]', '_', target)
    slug = re.sub(r'_+', '_', slug)
    slug = slug.strip('_').lower()

    if len(slug) < 3:
        slug = f"{slug}_{hashlib.md5(target.encode()).hexdigest()[:8]}"

    return slug


def _generate_session_id() -> str:
    """Generate a unique session ID."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    unique = str(uuid.uuid4())[:8]
    return f"session_{timestamp}_{unique}"


def _create_initial_target_profile(
    target: str,
    target_type: str,
    description: str = "",
    scope: list[str] | None = None,
    out_of_scope: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Create the initial target profile structure."""
    now = datetime.now(timezone.utc).isoformat()
    slug = _sanitize_target_slug(target)

    return {
        "id": str(uuid.uuid4())[:12],
        "slug": slug,
        "target": target,
        "target_type": target_type,
        "description": description,
        "created_at": now,
        "updated_at": now,
        "last_scan_at": None,
        "total_sessions": 0,
        "status": "initialized",
        "scope": {
            "in_scope": scope or [target],
            "out_of_scope": out_of_scope or [],
        },
        "tags": tags or [],
        "stats": {
            "total_findings": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
            "endpoints_discovered": 0,
            "technologies_identified": 0,
            "sessions_count": 0,
        },
        "quick_info": {
            "main_technologies": [],
            "confirmed_vulnerabilities": [],
            "key_endpoints": [],
            "authentication_status": "unknown",
            "last_session_summary": "",
        },
        "tested_areas": {
            "reconnaissance": [],
            "vulnerability_types": [],
            "endpoints_tested": [],
        },
        "pending_work": {
            "high_priority": [],
            "medium_priority": [],
            "low_priority": [],
            "follow_ups": [],
        },
        "session_history": [],
    }


def _create_session_data(
    session_id: str,
    target_slug: str,
    objective: str = "",
    focus_areas: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new session data structure."""
    now = datetime.now(timezone.utc).isoformat()

    return {
        "session_id": session_id,
        "target_slug": target_slug,
        "started_at": now,
        "ended_at": None,
        "duration_minutes": 0,
        "status": "active",
        "objective": objective,
        "focus_areas": focus_areas or [],
        "accomplishments": [],
        "findings": [],
        "endpoints": {
            "discovered": [],
            "tested": [],
            "vulnerable": [],
        },
        "technologies": [],
        "notes": [],
        "continuation_notes": {
            "immediate_follow_ups": [],
            "promising_leads": [],
            "blocked_by": [],
            "recommendations": [],
        },
        "metrics": {
            "findings_count": 0,
            "endpoints_discovered": 0,
            "endpoints_tested": 0,
        },
    }


def _get_or_create_target_file(
    config: dict[str, str],
    target_slug: str,
    file_name: str,
    default_content: dict[str, Any] | list[Any],
) -> tuple[dict[str, Any] | list[Any], str | None]:
    """Get existing file content or return default."""
    path = f"targets/{target_slug}/{file_name}"
    url = f"{config['api_base']}/repos/{config['repo']}/contents/{path}"

    try:
        response = requests.get(url, headers=_get_headers(config["token"]), timeout=30)

        if response.status_code == 200:
            data = response.json()
            content = json.loads(base64.b64decode(data.get("content", "")).decode())
            return content, data.get("sha")

        return default_content, None

    except (requests.RequestException, json.JSONDecodeError):
        return default_content, None


def _save_target_file(
    config: dict[str, str],
    target_slug: str,
    file_name: str,
    content: dict[str, Any] | list[Any],
    sha: str | None = None,
    commit_message: str = "",
) -> bool:
    """Save a file to the target's directory in StrixDB."""
    path = f"targets/{target_slug}/{file_name}"
    url = f"{config['api_base']}/repos/{config['repo']}/contents/{path}"

    content_encoded = base64.b64encode(json.dumps(content, indent=2).encode()).decode()

    payload: dict[str, Any] = {
        "message": commit_message or f"[StrixDB] Update {path}",
        "content": content_encoded,
        "branch": config["branch"],
    }

    if sha:
        payload["sha"] = sha

    try:
        response = requests.put(
            url,
            headers=_get_headers(config["token"]),
            json=payload,
            timeout=30,
        )
        return response.status_code in (200, 201)
    except requests.RequestException:
        return False


def _ensure_target_directory(config: dict[str, str], target_slug: str) -> bool:
    """Ensure the target directory exists in StrixDB."""
    readme_path = f"targets/{target_slug}/README.md"
    url = f"{config['api_base']}/repos/{config['repo']}/contents/{readme_path}"

    try:
        response = requests.get(url, headers=_get_headers(config["token"]), timeout=30)

        if response.status_code == 200:
            return True

        if response.status_code == 404:
            readme_content = f"""# Target: {target_slug}

This directory contains comprehensive scan data for target: `{target_slug}`

## Contents

- `profile.json` - Main target profile and metadata
- `sessions/` - Individual session data
- `findings.json` - Vulnerability findings
- `endpoints.json` - Discovered endpoints and paths
- `technologies.json` - Technology stack information
- `notes.json` - Session notes and observations

## Auto-generated by StrixDB Target Tracking System
"""
            content_encoded = base64.b64encode(readme_content.encode()).decode()

            create_response = requests.put(
                url,
                headers=_get_headers(config["token"]),
                json={
                    "message": f"[StrixDB] Initialize target: {target_slug}",
                    "content": content_encoded,
                    "branch": config["branch"],
                },
                timeout=30,
            )

            return create_response.status_code in (200, 201)

        return False

    except requests.RequestException:
        return False


@register_tool(sandbox_execution=False)
def strixdb_target_init(
    agent_state: Any,
    target: str,
    target_type: str = "web_app",
    description: str = "",
    scope: list[str] | None = None,
    out_of_scope: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Initialize a new target in StrixDB for comprehensive tracking."""
    config = _get_strixdb_config()

    if not config["repo"] or not config["token"]:
        return {
            "success": False,
            "error": "StrixDB not configured. Ensure STRIXDB_TOKEN is set.",
            "target": None,
        }

    target_slug = _sanitize_target_slug(target)

    existing_profile, existing_sha = _get_or_create_target_file(
        config, target_slug, "profile.json", {}
    )

    if existing_profile and existing_sha:
        return {
            "success": True,
            "message": f"Target '{target_slug}' already exists.",
            "is_new": False,
            "target": {
                "slug": target_slug,
                "profile": existing_profile,
                "previous_sessions_count": existing_profile.get("total_sessions", 0),
                "last_scan_at": existing_profile.get("last_scan_at"),
                "stats": existing_profile.get("stats", {}),
                "tested_areas": existing_profile.get("tested_areas", {}),
                "pending_work": existing_profile.get("pending_work", {}),
            },
        }

    if not _ensure_target_directory(config, target_slug):
        return {
            "success": False,
            "error": f"Failed to create target directory for '{target_slug}'",
            "target": None,
        }

    profile = _create_initial_target_profile(
        target=target,
        target_type=target_type,
        description=description,
        scope=scope,
        out_of_scope=out_of_scope,
        tags=tags,
    )

    if not _save_target_file(
        config,
        target_slug,
        "profile.json",
        profile,
        commit_message=f"[StrixDB] Initialize target profile: {target_slug}",
    ):
        return {
            "success": False,
            "error": f"Failed to save target profile for '{target_slug}'",
            "target": None,
        }

    empty_structures = {
        "endpoints.json": {"discovered": [], "tested": [], "vulnerable": []},
        "technologies.json": {"identified": [], "versions": {}},
        "notes.json": {"entries": []},
        "findings.json": {"vulnerabilities": [], "informational": []},
    }

    for file_name, content in empty_structures.items():
        _save_target_file(
            config,
            target_slug,
            file_name,
            content,
            commit_message=f"[StrixDB] Initialize {file_name} for {target_slug}",
        )

    logger.info(f"[StrixDB] Initialized new target: {target_slug}")

    return {
        "success": True,
        "message": f"Successfully initialized target '{target_slug}'",
        "is_new": True,
        "target": {
            "slug": target_slug,
            "profile": profile,
            "previous_sessions_count": 0,
        },
    }


@register_tool(sandbox_execution=False)
def strixdb_target_session_start(
    agent_state: Any,
    target: str,
    objective: str = "",
    focus_areas: list[str] | None = None,
) -> dict[str, Any]:
    """Start a new scan session for a target."""
    config = _get_strixdb_config()

    if not config["repo"] or not config["token"]:
        return {"success": False, "error": "StrixDB not configured", "session": None}

    target_slug = _sanitize_target_slug(target)

    profile, profile_sha = _get_or_create_target_file(
        config, target_slug, "profile.json", {}
    )

    if not profile or not profile_sha:
        return {
            "success": False,
            "error": f"Target '{target_slug}' not found. Initialize it first.",
            "session": None,
        }

    session_id = _generate_session_id()
    session_data = _create_session_data(
        session_id=session_id,
        target_slug=target_slug,
        objective=objective,
        focus_areas=focus_areas,
    )

    if not _save_target_file(
        config,
        target_slug,
        f"sessions/{session_id}.json",
        session_data,
        commit_message=f"[StrixDB] Start session {session_id}",
    ):
        return {"success": False, "error": "Failed to create session", "session": None}

    profile["status"] = "active"
    profile["last_scan_at"] = datetime.now(timezone.utc).isoformat()
    profile["total_sessions"] = profile.get("total_sessions", 0) + 1

    _save_target_file(
        config, target_slug, "profile.json", profile, sha=profile_sha,
        commit_message=f"[StrixDB] Start session {session_id}",
    )

    return {
        "success": True,
        "message": f"Session '{session_id}' started for '{target_slug}'",
        "session": {
            "session_id": session_id,
            "target_slug": target_slug,
            "objective": objective,
            "focus_areas": focus_areas or [],
        },
        "target_summary": {
            "previous_sessions": profile.get("total_sessions", 0) - 1,
            "stats": profile.get("stats", {}),
            "tested_areas": profile.get("tested_areas", {}),
            "pending_work": profile.get("pending_work", {}),
        },
    }


@register_tool(sandbox_execution=False)
def strixdb_target_add_finding(
    agent_state: Any,
    target: str,
    session_id: str,
    title: str,
    severity: str,
    vulnerability_type: str,
    description: str = "",
    proof_of_concept: str = "",
    affected_endpoint: str = "",
    impact: str = "",
    remediation: str = "",
) -> dict[str, Any]:
    """Add a vulnerability finding to a target."""
    config = _get_strixdb_config()

    if not config["repo"] or not config["token"]:
        return {"success": False, "error": "StrixDB not configured"}

    target_slug = _sanitize_target_slug(target)

    findings, findings_sha = _get_or_create_target_file(
        config, target_slug, "findings.json",
        {"vulnerabilities": [], "informational": []}
    )

    finding_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()

    new_finding = {
        "id": finding_id,
        "session_id": session_id,
        "title": title,
        "severity": severity.lower(),
        "vulnerability_type": vulnerability_type,
        "description": description,
        "proof_of_concept": proof_of_concept,
        "affected_endpoint": affected_endpoint,
        "impact": impact,
        "remediation": remediation,
        "status": "confirmed",
        "discovered_at": now,
    }

    if severity.lower() in ["critical", "high", "medium", "low"]:
        findings["vulnerabilities"].append(new_finding)
    else:
        findings["informational"].append(new_finding)

    _save_target_file(
        config, target_slug, "findings.json", findings, sha=findings_sha,
        commit_message=f"[StrixDB] Add finding: {title}",
    )

    # Update profile stats
    profile, profile_sha = _get_or_create_target_file(
        config, target_slug, "profile.json", {}
    )
    if profile:
        profile["stats"]["total_findings"] = profile["stats"].get("total_findings", 0) + 1
        profile["stats"][severity.lower()] = profile["stats"].get(severity.lower(), 0) + 1
        _save_target_file(config, target_slug, "profile.json", profile, sha=profile_sha)

    return {
        "success": True,
        "message": f"Finding '{title}' added successfully",
        "finding_id": finding_id,
    }


@register_tool(sandbox_execution=False)
def strixdb_target_add_endpoint(
    agent_state: Any,
    target: str,
    session_id: str,
    endpoint: str,
    method: str = "GET",
    parameters: list[str] | None = None,
    status: str = "discovered",
    vulnerable: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    """Add a discovered endpoint to a target."""
    config = _get_strixdb_config()

    if not config["repo"] or not config["token"]:
        return {"success": False, "error": "StrixDB not configured"}

    target_slug = _sanitize_target_slug(target)

    endpoints, endpoints_sha = _get_or_create_target_file(
        config, target_slug, "endpoints.json",
        {"discovered": [], "tested": [], "vulnerable": []}
    )

    endpoint_data = {
        "endpoint": endpoint,
        "method": method.upper(),
        "parameters": parameters or [],
        "status": status,
        "vulnerable": vulnerable,
        "notes": notes,
        "session_id": session_id,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }

    endpoints["discovered"].append(endpoint_data)
    if status == "tested":
        endpoints["tested"].append(endpoint)
    if vulnerable:
        endpoints["vulnerable"].append(endpoint)

    _save_target_file(
        config, target_slug, "endpoints.json", endpoints, sha=endpoints_sha,
        commit_message=f"[StrixDB] Add endpoint: {method} {endpoint}",
    )

    return {
        "success": True,
        "message": f"Endpoint '{method} {endpoint}' added successfully",
    }


@register_tool(sandbox_execution=False)
def strixdb_target_session_end(
    agent_state: Any,
    target: str,
    session_id: str,
    summary: str = "",
    accomplishments: list[str] | None = None,
    immediate_follow_ups: list[str] | None = None,
    promising_leads: list[str] | None = None,
) -> dict[str, Any]:
    """End a scan session with notes for continuation."""
    config = _get_strixdb_config()

    if not config["repo"] or not config["token"]:
        return {"success": False, "error": "StrixDB not configured"}

    target_slug = _sanitize_target_slug(target)

    session, session_sha = _get_or_create_target_file(
        config, target_slug, f"sessions/{session_id}.json", {}
    )

    if not session:
        return {"success": False, "error": f"Session '{session_id}' not found"}

    now = datetime.now(timezone.utc)
    started_at = datetime.fromisoformat(session["started_at"].replace("Z", "+00:00"))
    duration = (now - started_at).total_seconds() / 60

    session["ended_at"] = now.isoformat()
    session["duration_minutes"] = round(duration, 2)
    session["status"] = "completed"
    session["accomplishments"] = accomplishments or []
    session["continuation_notes"] = {
        "summary": summary,
        "immediate_follow_ups": immediate_follow_ups or [],
        "promising_leads": promising_leads or [],
    }

    _save_target_file(
        config, target_slug, f"sessions/{session_id}.json", session, sha=session_sha,
        commit_message=f"[StrixDB] End session {session_id}",
    )

    # Update profile
    profile, profile_sha = _get_or_create_target_file(
        config, target_slug, "profile.json", {}
    )
    if profile:
        profile["quick_info"]["last_session_summary"] = summary
        if immediate_follow_ups:
            profile["pending_work"]["high_priority"] = immediate_follow_ups
        if promising_leads:
            profile["pending_work"]["follow_ups"] = promising_leads
        _save_target_file(config, target_slug, "profile.json", profile, sha=profile_sha)

    return {
        "success": True,
        "message": f"Session '{session_id}' ended successfully",
        "duration_minutes": round(duration, 2),
    }


@register_tool(sandbox_execution=False)
def strixdb_target_get_summary(
    agent_state: Any,
    target: str,
) -> dict[str, Any]:
    """Get a comprehensive summary of a target."""
    config = _get_strixdb_config()

    if not config["repo"] or not config["token"]:
        return {"success": False, "error": "StrixDB not configured"}

    target_slug = _sanitize_target_slug(target)

    profile, _ = _get_or_create_target_file(config, target_slug, "profile.json", {})

    if not profile:
        return {"success": False, "error": f"Target '{target_slug}' not found"}

    findings, _ = _get_or_create_target_file(
        config, target_slug, "findings.json",
        {"vulnerabilities": [], "informational": []}
    )
    endpoints, _ = _get_or_create_target_file(
        config, target_slug, "endpoints.json",
        {"discovered": [], "tested": [], "vulnerable": []}
    )

    return {
        "success": True,
        "target_slug": target_slug,
        "profile": profile,
        "findings_count": len(findings.get("vulnerabilities", [])),
        "endpoints_discovered": len(endpoints.get("discovered", [])),
        "endpoints_tested": len(endpoints.get("tested", [])),
        "endpoints_vulnerable": len(endpoints.get("vulnerable", [])),
    }
