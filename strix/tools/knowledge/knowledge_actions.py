"""
Advanced Knowledge Management - Hierarchical knowledge organization.

This module provides an enhanced knowledge and notes system with:
- Hierarchical organization (collections and folders)
- Entry linking with typed relationships
- Priority levels
- Full-text search with relevance ranking
- Templates for common entry types
- Version history
- Cross-agent sharing
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)

# In-memory knowledge store (in production, this would be persisted)
_knowledge_store: dict[str, dict[str, Any]] = {}
_entry_links: list[dict[str, Any]] = []
_collections: dict[str, dict[str, Any]] = {}

# Relationship types
RELATIONSHIP_TYPES = [
    "related_to",
    "depends_on",
    "blocks",
    "references",
    "confirms",
    "contradicts",
    "extends",
    "duplicates",
]

# Template definitions
TEMPLATES = {
    "vulnerability": {
        "category": "findings",
        "priority": "high",
        "fields": ["title", "severity", "poc", "impact", "remediation"],
    },
    "credential": {
        "category": "credentials",
        "priority": "critical",
        "fields": ["service", "username", "password", "notes"],
    },
    "endpoint": {
        "category": "endpoints",
        "priority": "medium",
        "fields": ["url", "method", "parameters", "auth_required", "notes"],
    },
    "technique": {
        "category": "techniques",
        "priority": "medium",
        "fields": ["name", "description", "steps", "tools_needed"],
    },
    "bypass": {
        "category": "bypasses",
        "priority": "high",
        "fields": ["target", "technique", "payload", "success_rate"],
    },
}


def _generate_entry_id() -> str:
    """Generate a unique entry ID."""
    return f"ke_{str(uuid.uuid4())[:8]}"


@register_tool(sandbox_execution=False)
def create_knowledge_entry(
    agent_state: Any,
    title: str,
    content: str,
    category: str = "general",
    priority: str = "medium",
    tags: list[str] | None = None,
    collection: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a new knowledge entry with advanced organization.

    Args:
        agent_state: Current agent state
        title: Entry title
        content: Entry content
        category: Category (findings, credentials, endpoints, techniques, etc.)
        priority: Priority level (critical, high, medium, low)
        tags: Tags for categorization
        collection: Optional collection to add entry to
        metadata: Additional metadata

    Returns:
        Dictionary with created entry
    """
    entry_id = _generate_entry_id()
    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "id": entry_id,
        "title": title,
        "content": content,
        "category": category,
        "priority": priority,
        "tags": tags or [],
        "collection": collection,
        "metadata": metadata or {},
        "created_at": now,
        "updated_at": now,
        "version": 1,
        "history": [],
        "links": [],
    }

    _knowledge_store[entry_id] = entry

    if collection:
        if collection not in _collections:
            _collections[collection] = {
                "name": collection,
                "entries": [],
                "created_at": now,
            }
        _collections[collection]["entries"].append(entry_id)

    logger.info(f"[Knowledge] Created entry {entry_id}: {title}")

    return {
        "success": True,
        "message": f"Knowledge entry '{title}' created",
        "entry_id": entry_id,
        "entry": entry,
    }


@register_tool(sandbox_execution=False)
def update_knowledge_entry(
    agent_state: Any,
    entry_id: str,
    title: str | None = None,
    content: str | None = None,
    priority: str | None = None,
    tags: list[str] | None = None,
    append_content: str | None = None,
) -> dict[str, Any]:
    """
    Update an existing knowledge entry with version tracking.

    Args:
        agent_state: Current agent state
        entry_id: ID of entry to update
        title: New title (optional)
        content: New content (optional)
        priority: New priority (optional)
        tags: New tags (optional)
        append_content: Content to append (optional)

    Returns:
        Dictionary with updated entry
    """
    if entry_id not in _knowledge_store:
        return {"success": False, "error": f"Entry '{entry_id}' not found"}

    entry = _knowledge_store[entry_id]

    # Save current version to history
    entry["history"].append({
        "version": entry["version"],
        "content": entry["content"],
        "updated_at": entry["updated_at"],
    })

    # Update fields
    if title:
        entry["title"] = title
    if content:
        entry["content"] = content
    elif append_content:
        entry["content"] = f"{entry['content']}\n\n{append_content}"
    if priority:
        entry["priority"] = priority
    if tags is not None:
        entry["tags"] = tags

    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    entry["version"] += 1

    return {
        "success": True,
        "message": f"Entry '{entry_id}' updated to version {entry['version']}",
        "entry": entry,
    }


@register_tool(sandbox_execution=False)
def delete_knowledge_entry(
    agent_state: Any,
    entry_id: str,
) -> dict[str, Any]:
    """Delete a knowledge entry."""
    if entry_id not in _knowledge_store:
        return {"success": False, "error": f"Entry '{entry_id}' not found"}

    entry = _knowledge_store.pop(entry_id)

    # Remove from collections
    for collection in _collections.values():
        if entry_id in collection["entries"]:
            collection["entries"].remove(entry_id)

    # Remove links
    global _entry_links
    _entry_links = [
        link for link in _entry_links
        if link["source"] != entry_id and link["target"] != entry_id
    ]

    return {
        "success": True,
        "message": f"Entry '{entry['title']}' deleted",
    }


@register_tool(sandbox_execution=False)
def search_knowledge(
    agent_state: Any,
    query: str,
    category: list[str] | None = None,
    priority: list[str] | None = None,
    tags: list[str] | None = None,
    collection: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Full-text search with filtering and relevance ranking.

    Args:
        agent_state: Current agent state
        query: Search query
        category: Filter by categories
        priority: Filter by priorities
        tags: Filter by tags
        collection: Filter by collection
        limit: Maximum results

    Returns:
        Dictionary with search results
    """
    results = []
    query_lower = query.lower()

    for entry_id, entry in _knowledge_store.items():
        # Calculate relevance score
        score = 0

        # Title match (highest weight)
        if query_lower in entry["title"].lower():
            score += 10

        # Content match
        if query_lower in entry["content"].lower():
            score += 5

        # Tag match
        for tag in entry.get("tags", []):
            if query_lower in tag.lower():
                score += 3

        if score == 0:
            continue

        # Apply filters
        if category and entry["category"] not in category:
            continue
        if priority and entry["priority"] not in priority:
            continue
        if tags and not any(t in entry.get("tags", []) for t in tags):
            continue
        if collection and entry.get("collection") != collection:
            continue

        results.append({
            "entry_id": entry_id,
            "title": entry["title"],
            "category": entry["category"],
            "priority": entry["priority"],
            "score": score,
            "preview": entry["content"][:200] + "..." if len(entry["content"]) > 200 else entry["content"],
        })

    # Sort by relevance
    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "success": True,
        "query": query,
        "total_results": len(results),
        "results": results[:limit],
    }


@register_tool(sandbox_execution=False)
def link_entries(
    agent_state: Any,
    source_id: str,
    target_id: str,
    relationship_type: str = "related_to",
    notes: str = "",
) -> dict[str, Any]:
    """
    Create a typed link between two knowledge entries.

    Args:
        agent_state: Current agent state
        source_id: Source entry ID
        target_id: Target entry ID
        relationship_type: Type of relationship
        notes: Optional notes about the relationship

    Returns:
        Dictionary with link result
    """
    if relationship_type not in RELATIONSHIP_TYPES:
        return {
            "success": False,
            "error": f"Invalid relationship type. Must be one of: {RELATIONSHIP_TYPES}",
        }

    link = {
        "id": f"link_{str(uuid.uuid4())[:8]}",
        "source": source_id,
        "target": target_id,
        "relationship_type": relationship_type,
        "notes": notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    _entry_links.append(link)

    # Update entries if they exist in store
    if source_id in _knowledge_store:
        _knowledge_store[source_id]["links"].append({
            "target": target_id,
            "type": relationship_type,
        })
    if target_id in _knowledge_store:
        _knowledge_store[target_id]["links"].append({
            "source": source_id,
            "type": relationship_type,
        })

    return {
        "success": True,
        "message": f"Linked {source_id} -> {target_id} ({relationship_type})",
        "link": link,
    }


@register_tool(sandbox_execution=False)
def create_from_template(
    agent_state: Any,
    template_name: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a knowledge entry from a predefined template.

    Available templates: vulnerability, credential, endpoint, technique, bypass

    Args:
        agent_state: Current agent state
        template_name: Name of the template to use
        data: Data to fill the template

    Returns:
        Dictionary with created entry
    """
    if template_name not in TEMPLATES:
        return {
            "success": False,
            "error": f"Unknown template. Available: {list(TEMPLATES.keys())}",
        }

    template = TEMPLATES[template_name]

    # Build content from template fields
    content_parts = []
    for field in template["fields"]:
        if field in data:
            content_parts.append(f"**{field.title()}:** {data[field]}")

    content = "\n\n".join(content_parts)
    title = data.get("title", data.get("name", f"New {template_name.title()}"))

    return create_knowledge_entry(
        agent_state=agent_state,
        title=title,
        content=content,
        category=template["category"],
        priority=data.get("priority", template["priority"]),
        tags=data.get("tags", [template_name]),
        metadata={"template": template_name, "original_data": data},
    )


@register_tool(sandbox_execution=False)
def get_knowledge_stats(
    agent_state: Any,
) -> dict[str, Any]:
    """Get statistics about the knowledge base."""
    category_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}

    for entry in _knowledge_store.values():
        cat = entry["category"]
        pri = entry["priority"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        priority_counts[pri] = priority_counts.get(pri, 0) + 1

    return {
        "success": True,
        "total_entries": len(_knowledge_store),
        "total_links": len(_entry_links),
        "total_collections": len(_collections),
        "by_category": category_counts,
        "by_priority": priority_counts,
        "available_templates": list(TEMPLATES.keys()),
        "relationship_types": RELATIONSHIP_TYPES,
    }


@register_tool(sandbox_execution=False)
def list_knowledge_entries(
    agent_state: Any,
    category: str | None = None,
    collection: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List knowledge entries with optional filtering."""
    entries = []

    for entry_id, entry in _knowledge_store.items():
        if category and entry["category"] != category:
            continue
        if collection and entry.get("collection") != collection:
            continue

        entries.append({
            "entry_id": entry_id,
            "title": entry["title"],
            "category": entry["category"],
            "priority": entry["priority"],
            "tags": entry["tags"],
            "updated_at": entry["updated_at"],
        })

    # Sort by updated_at descending
    entries.sort(key=lambda x: x["updated_at"], reverse=True)

    return {
        "success": True,
        "total": len(entries),
        "entries": entries[:limit],
    }
