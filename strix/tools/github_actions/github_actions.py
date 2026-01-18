"""
GitHub Actions Integration Module.

This module provides tools for Strix agents to leverage GitHub Actions
for hosting, validation, development, generation, and automation tasks.
Uses the STRIXDB_TOKEN for full repository access including workflow management.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests

from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)

# GitHub API configuration
GITHUB_API_BASE = "https://api.github.com"
DEFAULT_STRIXDB_REPO = os.getenv("STRIXDB_REPO", "usestrix/strixdb")


def _get_github_token() -> str | None:
    """Get GitHub token from environment."""
    return os.getenv("STRIXDB_TOKEN") or os.getenv("GITHUB_TOKEN")


def _get_headers() -> dict[str, str]:
    """Get GitHub API headers."""
    token = _get_github_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_repo_parts(repo: str | None = None) -> tuple[str, str]:
    """Parse owner/repo from repository string."""
    repo = repo or DEFAULT_STRIXDB_REPO
    parts = repo.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repo format: {repo}. Expected 'owner/repo'")
    return parts[0], parts[1]


def _api_request(
    method: str,
    endpoint: str,
    data: dict | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Make a GitHub API request."""
    url = f"{GITHUB_API_BASE}{endpoint}"
    headers = _get_headers()
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=timeout)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=data, timeout=timeout)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, timeout=timeout)
        else:
            return {"success": False, "error": f"Unsupported method: {method}"}
        
        if response.status_code in (200, 201, 202, 204):
            if response.content:
                return {"success": True, "data": response.json()}
            return {"success": True}
        else:
            error_data = response.json() if response.content else {}
            return {
                "success": False,
                "error": error_data.get("message", f"HTTP {response.status_code}"),
                "status_code": response.status_code,
            }
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# WORKFLOW MANAGEMENT
# ============================================================================

@register_tool(sandbox_execution=False)
def github_create_workflow(
    agent_state: Any,
    workflow_name: str,
    workflow_content: str,
    repo: str | None = None,
    branch: str = "main",
    commit_message: str | None = None,
) -> dict[str, Any]:
    """
    Create a new GitHub Actions workflow file in a repository.

    Use this to create custom workflows for hosting, validation, testing,
    or any automation task. The workflow will be created in .github/workflows/

    Args:
        agent_state: Current agent state
        workflow_name: Name for the workflow file (e.g., 'my-scan.yml')
        workflow_content: Full YAML content of the workflow
        repo: Repository in 'owner/repo' format (defaults to STRIXDB_REPO)
        branch: Branch to create workflow on (default: main)
        commit_message: Optional commit message

    Returns:
        Dictionary with creation result and workflow URL

    Example workflow_content:
        name: My Custom Workflow
        on: workflow_dispatch
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - run: echo "Hello from workflow!"
    """
    if not _get_github_token():
        return {"success": False, "error": "STRIXDB_TOKEN not configured"}
    
    # Validate workflow name
    if not workflow_name.endswith(('.yml', '.yaml')):
        workflow_name = f"{workflow_name}.yml"
    
    workflow_name = re.sub(r'[^a-zA-Z0-9_\-.]', '_', workflow_name)
    path = f".github/workflows/{workflow_name}"
    
    try:
        owner, repo_name = _get_repo_parts(repo)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    
    # Encode content
    encoded_content = base64.b64encode(workflow_content.encode()).decode()
    
    # Check if file exists
    check_result = _api_request("GET", f"/repos/{owner}/{repo_name}/contents/{path}?ref={branch}")
    
    data = {
        "message": commit_message or f"Create workflow: {workflow_name}",
        "content": encoded_content,
        "branch": branch,
    }
    
    if check_result.get("success"):
        # Update existing file
        data["sha"] = check_result["data"]["sha"]
    
    result = _api_request("PUT", f"/repos/{owner}/{repo_name}/contents/{path}", data)
    
    if result.get("success"):
        logger.info(f"[GitHub Actions] Created workflow: {workflow_name}")
        return {
            "success": True,
            "message": f"Workflow '{workflow_name}' created successfully",
            "path": path,
            "repo": f"{owner}/{repo_name}",
            "workflow_url": f"https://github.com/{owner}/{repo_name}/actions",
            "file_url": f"https://github.com/{owner}/{repo_name}/blob/{branch}/{path}",
        }
    
    return result


@register_tool(sandbox_execution=False)
def github_trigger_workflow(
    agent_state: Any,
    workflow_id: str,
    repo: str | None = None,
    branch: str = "main",
    inputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Trigger a GitHub Actions workflow to run.

    Use this to start any workflow_dispatch workflow. Great for:
    - Running validation workflows
    - Starting build/test pipelines
    - Triggering deployment or hosting
    - Running custom automation

    Args:
        agent_state: Current agent state
        workflow_id: Workflow file name (e.g., 'build.yml') or workflow ID number
        repo: Repository in 'owner/repo' format
        branch: Branch to run workflow on (default: main)
        inputs: Optional workflow input parameters

    Returns:
        Dictionary with trigger result
    """
    if not _get_github_token():
        return {"success": False, "error": "STRIXDB_TOKEN not configured"}
    
    try:
        owner, repo_name = _get_repo_parts(repo)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    
    data = {"ref": branch}
    if inputs:
        data["inputs"] = inputs
    
    result = _api_request(
        "POST",
        f"/repos/{owner}/{repo_name}/actions/workflows/{workflow_id}/dispatches",
        data,
    )
    
    if result.get("success"):
        logger.info(f"[GitHub Actions] Triggered workflow: {workflow_id}")
        return {
            "success": True,
            "message": f"Workflow '{workflow_id}' triggered on branch '{branch}'",
            "repo": f"{owner}/{repo_name}",
            "runs_url": f"https://github.com/{owner}/{repo_name}/actions/workflows/{workflow_id}",
            "note": "Use github_get_workflow_runs to check status",
        }
    
    return result


@register_tool(sandbox_execution=False)
def github_get_workflow_runs(
    agent_state: Any,
    workflow_id: str | None = None,
    repo: str | None = None,
    status: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Get the status of workflow runs.

    Use to check if a triggered workflow completed successfully.

    Args:
        agent_state: Current agent state
        workflow_id: Optional workflow file name to filter by
        repo: Repository in 'owner/repo' format
        status: Filter by status (queued, in_progress, completed)
        limit: Maximum number of runs to return

    Returns:
        Dictionary with workflow run statuses
    """
    if not _get_github_token():
        return {"success": False, "error": "STRIXDB_TOKEN not configured"}
    
    try:
        owner, repo_name = _get_repo_parts(repo)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    
    params = []
    if status:
        params.append(f"status={status}")
    params.append(f"per_page={limit}")
    query = "&".join(params)
    
    if workflow_id:
        endpoint = f"/repos/{owner}/{repo_name}/actions/workflows/{workflow_id}/runs?{query}"
    else:
        endpoint = f"/repos/{owner}/{repo_name}/actions/runs?{query}"
    
    result = _api_request("GET", endpoint)
    
    if result.get("success"):
        runs = result["data"].get("workflow_runs", [])
        return {
            "success": True,
            "total_count": result["data"].get("total_count", 0),
            "runs": [
                {
                    "id": run["id"],
                    "name": run["name"],
                    "status": run["status"],
                    "conclusion": run.get("conclusion"),
                    "created_at": run["created_at"],
                    "url": run["html_url"],
                }
                for run in runs[:limit]
            ],
        }
    
    return result


@register_tool(sandbox_execution=False)
def github_list_workflows(
    agent_state: Any,
    repo: str | None = None,
) -> dict[str, Any]:
    """
    List all workflows in a repository.

    Args:
        agent_state: Current agent state
        repo: Repository in 'owner/repo' format

    Returns:
        Dictionary with list of available workflows
    """
    if not _get_github_token():
        return {"success": False, "error": "STRIXDB_TOKEN not configured"}
    
    try:
        owner, repo_name = _get_repo_parts(repo)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    
    result = _api_request("GET", f"/repos/{owner}/{repo_name}/actions/workflows")
    
    if result.get("success"):
        workflows = result["data"].get("workflows", [])
        return {
            "success": True,
            "workflows": [
                {
                    "id": wf["id"],
                    "name": wf["name"],
                    "path": wf["path"],
                    "state": wf["state"],
                }
                for wf in workflows
            ],
        }
    
    return result


# ============================================================================
# HOSTING & VALIDATION WORKFLOWS
# ============================================================================

@register_tool(sandbox_execution=False)
def github_create_hosting_workflow(
    agent_state: Any,
    app_name: str,
    build_command: str = "npm run build",
    install_command: str = "npm install",
    output_dir: str = "dist",
    repo: str | None = None,
    port: int = 3000,
) -> dict[str, Any]:
    """
    Create a workflow to host/deploy an application for testing.

    Use this for white-box scanning when you need to run the application
    to test it dynamically.

    Args:
        agent_state: Current agent state
        app_name: Name for the hosting workflow
        build_command: Command to build the application
        install_command: Command to install dependencies
        output_dir: Output directory after build
        repo: Repository to create workflow in
        port: Port to run the application on

    Returns:
        Dictionary with workflow creation result
    """
    workflow_content = f'''name: Host {app_name}

on:
  workflow_dispatch:
    inputs:
      duration_minutes:
        description: 'How long to keep the app running (minutes)'
        required: false
        default: '30'
        type: string

jobs:
  host:
    runs-on: ubuntu-latest
    timeout-minutes: ${{{{ fromJSON(github.event.inputs.duration_minutes || '30') + 5 }}}}
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Install Dependencies
        run: {install_command}
      
      - name: Build Application
        run: {build_command}
      
      - name: Start Application
        run: |
          # Start the application in background
          npx serve -s {output_dir} -p {port} &
          APP_PID=$!
          echo "Application started on port {port}"
          
          # Keep running for specified duration
          DURATION=${{{{ github.event.inputs.duration_minutes || '30' }}}}
          sleep $((DURATION * 60))
          
          kill $APP_PID 2>/dev/null || true
          echo "Application stopped after $DURATION minutes"
      
      - name: Upload Build Artifacts
        uses: actions/upload-artifact@v4
        with:
          name: {app_name}-build
          path: {output_dir}
'''
    
    return github_create_workflow(
        agent_state=agent_state,
        workflow_name=f"host-{app_name}.yml",
        workflow_content=workflow_content,
        repo=repo,
        commit_message=f"Create hosting workflow for {app_name}",
    )


@register_tool(sandbox_execution=False)
def github_create_validation_workflow(
    agent_state: Any,
    name: str,
    validation_script: str,
    setup_commands: list[str] | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """
    Create a validation workflow to verify exploits or test findings.

    Use this to automatically validate vulnerabilities in a clean environment.

    Args:
        agent_state: Current agent state
        name: Name for the validation workflow
        validation_script: The script content to run for validation
        setup_commands: Optional list of setup commands to run first
        repo: Repository to create workflow in

    Returns:
        Dictionary with workflow creation result
    """
    setup_steps = ""
    if setup_commands:
        setup_steps = "\n".join([f"          {cmd}" for cmd in setup_commands])
        setup_steps = f'''
      - name: Setup Environment
        run: |
{setup_steps}
'''

    # Escape the script for YAML
    escaped_script = validation_script.replace("'", "''")
    
    workflow_content = f'''name: Validate {name}

on:
  workflow_dispatch:
    inputs:
      target_url:
        description: 'Target URL to validate against'
        required: false
        type: string
      additional_args:
        description: 'Additional arguments for validation'
        required: false
        type: string

env:
  TARGET_URL: ${{{{ github.event.inputs.target_url }}}}

jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install Tools
        run: |
          pip install requests httpx aiohttp
          sudo apt-get update && sudo apt-get install -y curl jq nmap
{setup_steps}
      
      - name: Run Validation
        id: validate
        run: |
          cat << 'VALIDATION_SCRIPT' > validate.py
{escaped_script}
VALIDATION_SCRIPT
          python validate.py ${{{{ github.event.inputs.additional_args }}}}
      
      - name: Save Results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: validation-results-{name}
          path: |
            *.log
            *.json
            *.txt
            validation_*
'''
    
    return github_create_workflow(
        agent_state=agent_state,
        workflow_name=f"validate-{name}.yml",
        workflow_content=workflow_content,
        repo=repo,
        commit_message=f"Create validation workflow: {name}",
    )


@register_tool(sandbox_execution=False)
def github_create_scanner_workflow(
    agent_state: Any,
    name: str,
    target: str,
    scan_commands: list[str],
    repo: str | None = None,
) -> dict[str, Any]:
    """
    Create a workflow to run security scanning tools.

    Use this to offload heavy scanning tasks to GitHub Actions runners.

    Args:
        agent_state: Current agent state
        name: Name for the scanner workflow
        target: Target to scan
        scan_commands: List of scan commands to execute
        repo: Repository to create workflow in

    Returns:
        Dictionary with workflow creation result
    """
    commands_yaml = "\n".join([f"          {cmd}" for cmd in scan_commands])
    
    workflow_content = f'''name: Security Scan - {name}

on:
  workflow_dispatch:
    inputs:
      target_override:
        description: 'Override target (leave empty to use default)'
        required: false
        type: string

env:
  DEFAULT_TARGET: "{target}"

jobs:
  scan:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Install Security Tools
        run: |
          pip install semgrep bandit sqlmap
          curl -sSfL https://github.com/projectdiscovery/nuclei/releases/download/v3.2.9/nuclei_3.2.9_linux_amd64.zip -o /tmp/nuclei.zip
          unzip -q /tmp/nuclei.zip -d /usr/local/bin
          nuclei -update-templates || true
          sudo apt-get update && sudo apt-get install -y nmap nikto
      
      - name: Set Target
        run: |
          TARGET="${{{{ github.event.inputs.target_override || env.DEFAULT_TARGET }}}}"
          echo "TARGET=$TARGET" >> $GITHUB_ENV
          echo "Scanning target: $TARGET"
      
      - name: Run Scans
        run: |
{commands_yaml}
      
      - name: Upload Results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: scan-results-{name}
          path: |
            *.json
            *.txt
            *.log
            *_results*
            *_output*
'''
    
    return github_create_workflow(
        agent_state=agent_state,
        workflow_name=f"scan-{name}.yml",
        workflow_content=workflow_content,
        repo=repo,
        commit_message=f"Create scanner workflow: {name}",
    )


# ============================================================================
# GENERAL PURPOSE WORKFLOWS
# ============================================================================

@register_tool(sandbox_execution=False)
def github_create_custom_workflow(
    agent_state: Any,
    name: str,
    description: str,
    steps: list[dict[str, Any]],
    triggers: list[str] | None = None,
    inputs: dict[str, dict[str, str]] | None = None,
    env_vars: dict[str, str] | None = None,
    timeout_minutes: int = 60,
    repo: str | None = None,
) -> dict[str, Any]:
    """
    Create a fully custom GitHub Actions workflow.

    This is the most flexible tool - use it for any automation need:
    - Hosting applications for testing
    - Running validation scripts
    - Building and deploying code
    - Data gathering and processing
    - Any automation task

    Args:
        agent_state: Current agent state
        name: Workflow name
        description: Description of what the workflow does
        steps: List of step definitions, each with 'name' and either 'run' or 'uses'
        triggers: List of triggers (e.g., ['workflow_dispatch', 'push'])
        inputs: Workflow dispatch inputs definition
        env_vars: Environment variables for the workflow
        timeout_minutes: Job timeout in minutes
        repo: Repository to create workflow in

    Returns:
        Dictionary with workflow creation result

    Example steps:
        [
            {"name": "Checkout", "uses": "actions/checkout@v4"},
            {"name": "Run Script", "run": "echo 'Hello'"},
            {"name": "Upload", "uses": "actions/upload-artifact@v4", "with": {"name": "output", "path": "*.txt"}}
        ]
    """
    # Build triggers
    triggers = triggers or ["workflow_dispatch"]
    trigger_yaml = "on:\n"
    
    for trigger in triggers:
        if trigger == "workflow_dispatch" and inputs:
            trigger_yaml += "  workflow_dispatch:\n    inputs:\n"
            for input_name, input_config in inputs.items():
                trigger_yaml += f"      {input_name}:\n"
                for key, value in input_config.items():
                    trigger_yaml += f"        {key}: '{value}'\n"
        else:
            trigger_yaml += f"  {trigger}:\n"
    
    # Build env vars
    env_yaml = ""
    if env_vars:
        env_yaml = "env:\n"
        for key, value in env_vars.items():
            env_yaml += f"  {key}: '{value}'\n"
    
    # Build steps
    steps_yaml = ""
    for step in steps:
        steps_yaml += f"      - name: {step['name']}\n"
        if "uses" in step:
            steps_yaml += f"        uses: {step['uses']}\n"
            if "with" in step:
                steps_yaml += "        with:\n"
                for key, value in step["with"].items():
                    steps_yaml += f"          {key}: {value}\n"
        if "run" in step:
            if "\n" in step["run"]:
                steps_yaml += "        run: |\n"
                for line in step["run"].split("\n"):
                    steps_yaml += f"          {line}\n"
            else:
                steps_yaml += f"        run: {step['run']}\n"
        if "env" in step:
            steps_yaml += "        env:\n"
            for key, value in step["env"].items():
                steps_yaml += f"          {key}: {value}\n"
    
    workflow_content = f'''# {description}
name: {name}

{trigger_yaml}
{env_yaml}
jobs:
  main:
    runs-on: ubuntu-latest
    timeout-minutes: {timeout_minutes}
    
    steps:
{steps_yaml}
'''
    
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '-', name.lower())
    
    return github_create_workflow(
        agent_state=agent_state,
        workflow_name=f"{safe_name}.yml",
        workflow_content=workflow_content,
        repo=repo,
        commit_message=f"Create workflow: {name}",
    )


@register_tool(sandbox_execution=False)
def github_get_workflow_artifacts(
    agent_state: Any,
    run_id: int,
    repo: str | None = None,
) -> dict[str, Any]:
    """
    Get artifacts from a workflow run.

    Use this to retrieve results from validation or scanning workflows.

    Args:
        agent_state: Current agent state
        run_id: The workflow run ID
        repo: Repository in 'owner/repo' format

    Returns:
        Dictionary with list of artifacts and download URLs
    """
    if not _get_github_token():
        return {"success": False, "error": "STRIXDB_TOKEN not configured"}
    
    try:
        owner, repo_name = _get_repo_parts(repo)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    
    result = _api_request("GET", f"/repos/{owner}/{repo_name}/actions/runs/{run_id}/artifacts")
    
    if result.get("success"):
        artifacts = result["data"].get("artifacts", [])
        return {
            "success": True,
            "run_id": run_id,
            "artifacts": [
                {
                    "id": a["id"],
                    "name": a["name"],
                    "size_bytes": a["size_in_bytes"],
                    "created_at": a["created_at"],
                    "download_url": a["archive_download_url"],
                }
                for a in artifacts
            ],
        }
    
    return result


@register_tool(sandbox_execution=False)
def github_delete_workflow(
    agent_state: Any,
    workflow_path: str,
    repo: str | None = None,
    branch: str = "main",
) -> dict[str, Any]:
    """
    Delete a workflow file from the repository.

    Use this to clean up temporary workflows after they're no longer needed.

    Args:
        agent_state: Current agent state
        workflow_path: Path to workflow file (e.g., '.github/workflows/my-workflow.yml')
        repo: Repository in 'owner/repo' format
        branch: Branch to delete from

    Returns:
        Dictionary with deletion result
    """
    if not _get_github_token():
        return {"success": False, "error": "STRIXDB_TOKEN not configured"}
    
    try:
        owner, repo_name = _get_repo_parts(repo)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    
    # Get file SHA
    check_result = _api_request("GET", f"/repos/{owner}/{repo_name}/contents/{workflow_path}?ref={branch}")
    
    if not check_result.get("success"):
        return {"success": False, "error": f"Workflow not found: {workflow_path}"}
    
    sha = check_result["data"]["sha"]
    
    result = _api_request(
        "DELETE",
        f"/repos/{owner}/{repo_name}/contents/{workflow_path}",
        {"message": f"Delete workflow: {workflow_path}", "sha": sha, "branch": branch},
    )
    
    if result.get("success"):
        logger.info(f"[GitHub Actions] Deleted workflow: {workflow_path}")
        return {
            "success": True,
            "message": f"Workflow '{workflow_path}' deleted successfully",
        }
    
    return result
