"""
Timeframe Tracking Module - Scan duration management with notifications.

This module provides tools for agents to track their remaining time,
receive threshold-based notifications, and save continuation state
for resuming scans in future sessions.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)

# Module-level storage for timeframe data
_scan_start_time: float | None = None
_scan_duration_minutes: int = 60
_notified_thresholds: set[int] = set()  # Track which thresholds have been notified
_last_check_time: float = 0

# Notification thresholds (minutes remaining)
NOTIFICATION_THRESHOLDS = {
    30: {
        "level": "CAUTION",
        "emoji": "⚠️",
        "message": "30 MINUTES REMAINING - Be cautious with time. Prioritize high-value tests.",
        "action": "Start wrapping up long-running scans. Focus on priority targets.",
    },
    15: {
        "level": "WARNING", 
        "emoji": "🔶",
        "message": "15 MINUTES REMAINING - Time to finish up. Complete current tests.",
        "action": "Stop starting new major tests. Finish current work. Prepare findings.",
    },
    5: {
        "level": "CRITICAL",
        "emoji": "🚨",
        "message": "5 MINUTES REMAINING - IMMEDIATELY finish up!",
        "action": "STOP all testing. File ALL reports. Save continuation state to StrixDB. Document where you stopped.",
    },
    2: {
        "level": "FINAL",
        "emoji": "⏰",
        "message": "2 MINUTES REMAINING - Final wrap-up!",
        "action": "Complete final report ONLY. Ensure all findings are saved.",
    },
}


def _initialize_from_env() -> None:
    """Initialize timeframe from environment variables."""
    global _scan_start_time, _scan_duration_minutes

    start_time_str = os.getenv("STRIX_SCAN_START_TIME")
    if start_time_str:
        try:
            _scan_start_time = float(start_time_str)
        except ValueError:
            _scan_start_time = time.time()
    else:
        _scan_start_time = time.time()

    duration_str = os.getenv("STRIX_SCAN_DURATION_MINUTES", "60")
    try:
        _scan_duration_minutes = int(duration_str)
    except ValueError:
        _scan_duration_minutes = 60


# Initialize on module load
_initialize_from_env()


def _check_and_get_notifications(remaining_minutes: float) -> list[dict[str, Any]]:
    """Check thresholds and return any new notifications."""
    global _notified_thresholds
    
    notifications = []
    
    for threshold_minutes, notification in sorted(NOTIFICATION_THRESHOLDS.items(), reverse=True):
        if remaining_minutes <= threshold_minutes and threshold_minutes not in _notified_thresholds:
            _notified_thresholds.add(threshold_minutes)
            notifications.append({
                "threshold_minutes": threshold_minutes,
                "level": notification["level"],
                "emoji": notification["emoji"],
                "message": notification["message"],
                "action": notification["action"],
                "remaining_minutes": round(remaining_minutes, 1),
            })
    
    return notifications


@register_tool(sandbox_execution=False)
def get_remaining_time(agent_state: Any) -> dict[str, Any]:
    """
    Get the remaining time in the current scan session.

    This function also checks for threshold notifications and returns them
    when time limits are approaching. Pay attention to any notifications!

    Returns:
        Dictionary with:
        - remaining_minutes: Minutes remaining (float)
        - remaining_seconds: Total seconds remaining
        - elapsed_minutes: Minutes elapsed since start
        - elapsed_percent: Percentage of time used (0-100)
        - is_critical: True if less than 10% time remains
        - recommendation: What to do based on remaining time
        - notifications: List of threshold notifications (if any triggered)
    """
    global _scan_start_time, _scan_duration_minutes, _last_check_time

    if _scan_start_time is None:
        _initialize_from_env()

    current_time = time.time()
    _last_check_time = current_time
    
    elapsed_seconds = current_time - (_scan_start_time or current_time)
    elapsed_minutes = elapsed_seconds / 60

    total_seconds = _scan_duration_minutes * 60
    remaining_seconds = max(0, total_seconds - elapsed_seconds)
    remaining_minutes = remaining_seconds / 60

    elapsed_percent = min(100, (elapsed_seconds / total_seconds) * 100) if total_seconds > 0 else 100

    # Check for new notifications
    notifications = _check_and_get_notifications(remaining_minutes)

    # Determine criticality and recommendations
    is_critical = remaining_minutes <= 5
    is_warning = remaining_minutes <= 15
    is_caution = remaining_minutes <= 30

    if remaining_minutes <= 2:
        recommendation = "🚨 FINAL - Complete report NOW. Save ALL state to StrixDB for continuation."
    elif remaining_minutes <= 5:
        recommendation = "🚨 CRITICAL - STOP testing! File ALL reports. Save continuation state immediately."
    elif remaining_minutes <= 15:
        recommendation = "🔶 WARNING - Finish current tests. Document findings. Prepare for wrap-up."
    elif remaining_minutes <= 30:
        recommendation = "⚠️ CAUTION - Be mindful of time. Prioritize remaining high-value tests."
    elif elapsed_percent >= 50:
        recommendation = "GOOD - Continue testing but start planning wrap-up phase."
    else:
        recommendation = "PLENTY OF TIME - Continue comprehensive testing."

    result = {
        "success": True,
        "remaining_minutes": round(remaining_minutes, 2),
        "remaining_seconds": int(remaining_seconds),
        "elapsed_minutes": round(elapsed_minutes, 2),
        "elapsed_percent": round(elapsed_percent, 1),
        "total_minutes": _scan_duration_minutes,
        "is_critical": is_critical,
        "is_warning": is_warning,
        "is_caution": is_caution,
        "recommendation": recommendation,
        "started_at": datetime.fromtimestamp(_scan_start_time or time.time(), tz=timezone.utc).isoformat(),
    }
    
    # Add notifications if any were triggered
    if notifications:
        result["notifications"] = notifications
        result["ATTENTION"] = f"⚠️ TIME ALERT: {notifications[0]['message']}"
    
    return result


@register_tool(sandbox_execution=False)
def get_elapsed_time(agent_state: Any) -> dict[str, Any]:
    """Get the elapsed time since scan start."""
    return get_remaining_time(agent_state)


@register_tool(sandbox_execution=False)
def is_timeframe_critical(agent_state: Any) -> dict[str, Any]:
    """
    Quick check if the timeframe is critical.

    Returns:
        Dictionary with criticality status and recommendations
    """
    time_info = get_remaining_time(agent_state)
    remaining = time_info["remaining_minutes"]

    return {
        "success": True,
        "is_critical": remaining <= 5,
        "is_warning": remaining <= 15,
        "is_caution": remaining <= 30,
        "should_wrap_up": remaining <= 15,
        "should_save_state": remaining <= 5,
        "remaining_minutes": remaining,
        "elapsed_percent": time_info["elapsed_percent"],
        "action_required": time_info.get("ATTENTION"),
    }


@register_tool(sandbox_execution=False)
def set_scan_timeframe(
    agent_state: Any,
    duration_minutes: int,
    reset_start_time: bool = True,
) -> dict[str, Any]:
    """Set or reset the scan timeframe."""
    global _scan_start_time, _scan_duration_minutes, _notified_thresholds

    if duration_minutes < 1:
        return {"success": False, "error": "Duration must be at least 1 minute"}

    if duration_minutes > 720:
        return {"success": False, "error": "Duration cannot exceed 720 minutes"}

    _scan_duration_minutes = duration_minutes
    _notified_thresholds.clear()  # Reset notifications for new timeframe

    if reset_start_time:
        _scan_start_time = time.time()

    logger.info(f"[Timeframe] Set duration to {duration_minutes} minutes")

    return {
        "success": True,
        "message": f"Timeframe set to {duration_minutes} minutes",
        "duration_minutes": duration_minutes,
        "started_at": datetime.fromtimestamp(_scan_start_time, tz=timezone.utc).isoformat(),
        "notification_thresholds": list(NOTIFICATION_THRESHOLDS.keys()),
    }


@register_tool(sandbox_execution=False)
def should_continue_scanning(agent_state: Any) -> dict[str, Any]:
    """
    Determine if the agent should continue scanning or wrap up.

    IMPORTANT: Even when vulnerabilities are found, continue scanning
    until the timeframe is exhausted. Only stop when time runs out.

    Returns:
        Dictionary with continuation decision and instructions
    """
    time_info = get_remaining_time(agent_state)
    remaining_minutes = time_info["remaining_minutes"]

    should_continue = remaining_minutes > 0.5
    should_start_new_tests = remaining_minutes > 15
    should_save_continuation = remaining_minutes <= 5

    if remaining_minutes <= 0.5:
        reason = "Timeframe exhausted. Complete final report and finish."
        action = "Use save_scan_continuation_state to save progress for next scan."
    elif remaining_minutes <= 2:
        reason = f"Only {remaining_minutes:.1f} minutes! FINAL wrap-up."
        action = "Complete report, save continuation state, finish immediately."
    elif remaining_minutes <= 5:
        reason = f"{remaining_minutes:.1f} minutes left. CRITICAL phase."
        action = "STOP testing. File ALL reports. Save continuation state to StrixDB."
    elif remaining_minutes <= 15:
        reason = f"{remaining_minutes:.1f} minutes left. Finish up."
        action = "Complete current tests. Document all findings. Prepare final report."
    elif remaining_minutes <= 30:
        reason = f"{remaining_minutes:.1f} minutes left. Be cautious."
        action = "Finish long-running scans. Focus on high-priority targets."
    else:
        reason = f"{remaining_minutes:.1f} minutes available."
        action = "Continue comprehensive testing."

    return {
        "success": True,
        "should_continue": should_continue,
        "should_start_new_tests": should_start_new_tests,
        "should_save_continuation": should_save_continuation,
        "remaining_minutes": remaining_minutes,
        "elapsed_percent": time_info["elapsed_percent"],
        "reason": reason,
        "action": action,
        "reminder": "Continue until timeframe exhausted! Save continuation state when time is critical.",
    }


@register_tool(sandbox_execution=False)
def save_scan_continuation_state(
    agent_state: Any,
    target: str,
    completed_phases: list[str],
    pending_tests: list[str],
    findings_summary: str,
    notes: str = "",
    priority_followups: list[str] | None = None,
) -> dict[str, Any]:
    """
    Save the current scan state to StrixDB for continuation in the next session.

    CALL THIS when less than 5 minutes remain! This ensures you can continue
    where you left off in the next scan.

    Args:
        agent_state: Current agent state
        target: Target being scanned
        completed_phases: List of completed testing phases
        pending_tests: List of tests that still need to be done
        findings_summary: Summary of vulnerabilities found so far
        notes: Additional notes for continuation
        priority_followups: High-priority items for next session

    Returns:
        Dictionary with save confirmation
    """
    continuation_state = {
        "target": target,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "completed_phases": completed_phases,
        "pending_tests": pending_tests,
        "findings_summary": findings_summary,
        "notes": notes,
        "priority_followups": priority_followups or [],
        "time_info": {
            "original_duration_minutes": _scan_duration_minutes,
            "time_used_minutes": round(
                (time.time() - (_scan_start_time or time.time())) / 60, 2
            ),
        },
    }

    # Try to save to StrixDB
    try:
        from strix.tools.strixdb.strixdb_targets import (
            strixdb_target_session_end,
            _sanitize_target_slug,
        )
        
        # Save as session end with continuation notes
        target_slug = _sanitize_target_slug(target)
        
        # Also create a continuation file in targets
        from strix.tools.strixdb.strixdb_actions import strixdb_save
        
        result = strixdb_save(
            agent_state=agent_state,
            name=f"continuation_{target_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            category="targets",
            subcategory=target_slug,
            content=json.dumps(continuation_state, indent=2),
            tags=["continuation", "scan-state", target_slug],
        )
        
        logger.info(f"[Timeframe] Saved continuation state for {target}")
        
        return {
            "success": True,
            "message": f"Continuation state saved for '{target}'",
            "state": continuation_state,
            "strixdb_result": result,
            "next_steps": (
                "On next scan, load this continuation state to resume where you left off. "
                "Use strixdb_search with tag 'continuation' to find saved states."
            ),
        }
        
    except Exception as e:
        logger.warning(f"[Timeframe] Failed to save to StrixDB: {e}")
        return {
            "success": True,
            "message": "Continuation state prepared (StrixDB save failed)",
            "state": continuation_state,
            "error": str(e),
            "fallback": "Include continuation state in your final report manually.",
        }


@register_tool(sandbox_execution=False)
def load_continuation_state(
    agent_state: Any,
    target: str,
) -> dict[str, Any]:
    """
    Load a previously saved continuation state for a target.

    Call this at the start of a scan to check if there's saved state
    from a previous session that was interrupted.

    Args:
        agent_state: Current agent state
        target: Target to load state for

    Returns:
        Dictionary with continuation state if found
    """
    try:
        from strix.tools.strixdb.strixdb_actions import strixdb_search
        from strix.tools.strixdb.strixdb_targets import _sanitize_target_slug
        
        target_slug = _sanitize_target_slug(target)
        
        result = strixdb_search(
            agent_state=agent_state,
            query=f"continuation_{target_slug}",
            category="targets",
        )
        
        if result.get("success") and result.get("results"):
            latest = result["results"][0]  # Most recent
            return {
                "success": True,
                "found": True,
                "message": f"Found continuation state for '{target}'",
                "continuation": latest,
                "recommendation": (
                    "Review the pending_tests and priority_followups from the saved state. "
                    "Skip completed_phases and continue from where the previous scan stopped."
                ),
            }
        
        return {
            "success": True,
            "found": False,
            "message": f"No continuation state found for '{target}'",
            "recommendation": "Start fresh scan from the beginning.",
        }
        
    except Exception as e:
        return {
            "success": False,
            "found": False,
            "error": str(e),
            "recommendation": "Start fresh scan.",
        }
