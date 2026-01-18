"""
Timeframe Tracking Module - Scan duration management with adaptive notifications.

This module provides tools for agents to track their remaining time,
receive percentage-based threshold notifications that scale with ANY timeframe,
and save continuation state for resuming scans in future sessions.
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
_notified_thresholds: set[str] = set()  # Track which thresholds have been notified (use string keys)
_last_check_time: float = 0

# Percentage-based notification thresholds (scales with ANY timeframe)
# Key: percentage of time REMAINING (not elapsed)
PERCENTAGE_THRESHOLDS = {
    25: {  # 25% of time remaining
        "level": "CAUTION",
        "emoji": "⚠️",
        "message_template": "{remaining:.0f} MINUTES REMAINING ({pct}% left) - Be cautious with time. Prioritize high-value tests.",
        "action": "Start wrapping up long-running scans. Focus on priority targets.",
    },
    15: {  # 15% of time remaining
        "level": "WARNING",
        "emoji": "🔶",
        "message_template": "{remaining:.0f} MINUTES REMAINING ({pct}% left) - Time to finish up. Complete current tests.",
        "action": "Stop starting new major tests. Finish current work. Prepare findings.",
    },
    8: {  # 8% of time remaining (~5 min for 60 min scan)
        "level": "CRITICAL",
        "emoji": "🚨",
        "message_template": "{remaining:.0f} MINUTES REMAINING ({pct}% left) - IMMEDIATELY finish up!",
        "action": "STOP all testing. File ALL reports. Save continuation state to StrixDB.",
    },
    3: {  # 3% of time remaining (~2 min for 60 min scan)
        "level": "FINAL",
        "emoji": "⏰",
        "message_template": "{remaining:.0f} MINUTES REMAINING ({pct}% left) - Final wrap-up!",
        "action": "Complete final report ONLY. Ensure all findings are saved.",
    },
}

# Minimum minutes for notifications (avoid spamming on very short scans)
MIN_NOTIFICATION_MINUTES = {
    "CAUTION": 2,   # Don't notify CAUTION if less than 2 min remaining
    "WARNING": 1,   # Don't notify WARNING if less than 1 min remaining
    "CRITICAL": 0.5,  # Don't notify CRITICAL if less than 30 sec remaining
    "FINAL": 0.25,  # Don't notify FINAL if less than 15 sec remaining
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


def _calculate_thresholds(total_minutes: int) -> dict[str, dict[str, Any]]:
    """
    Calculate actual minute thresholds based on total scan duration.
    
    Returns thresholds with actual minutes calculated from percentages.
    This ensures thresholds work reasonably for any timeframe:
    - 10 min scan: 2.5/1.5/0.8/0.3 min
    - 30 min scan: 7.5/4.5/2.4/0.9 min
    - 60 min scan: 15/9/4.8/1.8 min
    - 120 min scan: 30/18/9.6/3.6 min
    - 720 min scan: 180/108/57.6/21.6 min
    """
    thresholds = {}
    
    for pct, config in PERCENTAGE_THRESHOLDS.items():
        actual_minutes = (pct / 100) * total_minutes
        min_required = MIN_NOTIFICATION_MINUTES.get(config["level"], 0)
        
        # Only add threshold if it meets minimum time requirement
        if actual_minutes >= min_required:
            thresholds[f"pct_{pct}"] = {
                "percentage": pct,
                "minutes": actual_minutes,
                "level": config["level"],
                "emoji": config["emoji"],
                "message_template": config["message_template"],
                "action": config["action"],
            }
    
    return thresholds


def _check_and_get_notifications(remaining_minutes: float, total_minutes: int) -> list[dict[str, Any]]:
    """Check thresholds and return any new notifications based on percentage of time remaining."""
    global _notified_thresholds
    
    notifications = []
    remaining_percent = (remaining_minutes / total_minutes * 100) if total_minutes > 0 else 0
    
    thresholds = _calculate_thresholds(total_minutes)
    
    # Sort by percentage descending (fire higher percentage alerts first)
    sorted_thresholds = sorted(thresholds.items(), key=lambda x: x[1]["percentage"], reverse=True)
    
    for threshold_key, config in sorted_thresholds:
        pct_threshold = config["percentage"]
        min_threshold = config["minutes"]
        
        # Check if we crossed this threshold and haven't notified yet
        if remaining_percent <= pct_threshold and threshold_key not in _notified_thresholds:
            # Extra check: don't fire if remaining is below minimum
            if remaining_minutes >= MIN_NOTIFICATION_MINUTES.get(config["level"], 0):
                _notified_thresholds.add(threshold_key)
                
                message = config["message_template"].format(
                    remaining=remaining_minutes,
                    pct=round(remaining_percent, 0)
                )
                
                notifications.append({
                    "threshold_percent": pct_threshold,
                    "threshold_minutes": round(min_threshold, 1),
                    "level": config["level"],
                    "emoji": config["emoji"],
                    "message": message,
                    "action": config["action"],
                    "remaining_minutes": round(remaining_minutes, 1),
                    "remaining_percent": round(remaining_percent, 1),
                })
    
    return notifications


def _get_phase_recommendation(remaining_percent: float, remaining_minutes: float) -> str:
    """Get phase-appropriate recommendation based on remaining time percentage."""
    if remaining_percent <= 3 or remaining_minutes <= 1:
        return "⏰ FINAL - Complete report NOW. Save ALL state to StrixDB for continuation."
    elif remaining_percent <= 8 or remaining_minutes <= 3:
        return "🚨 CRITICAL - STOP testing! File ALL reports. Save continuation state immediately."
    elif remaining_percent <= 15 or remaining_minutes <= 5:
        return "🔶 WARNING - Finish current tests. Document findings. Prepare for wrap-up."
    elif remaining_percent <= 25 or remaining_minutes <= 10:
        return "⚠️ CAUTION - Be mindful of time. Prioritize remaining high-value tests."
    elif remaining_percent <= 50:
        return "GOOD - Continue testing but start planning wrap-up phase."
    else:
        return "PLENTY OF TIME - Continue comprehensive testing."


@register_tool(sandbox_execution=False)
def get_remaining_time(agent_state: Any) -> dict[str, Any]:
    """
    Get the remaining time in the current scan session.

    This function uses PERCENTAGE-BASED thresholds that automatically scale
    to any timeframe (10 min, 60 min, 720 min, etc.). Pay attention to any
    notifications returned - they indicate time thresholds have been crossed!

    Returns:
        Dictionary with:
        - remaining_minutes: Minutes remaining (float)
        - remaining_percent: Percentage of time remaining
        - elapsed_minutes: Minutes elapsed since start
        - elapsed_percent: Percentage of time used (0-100)
        - total_minutes: Total scan duration
        - phase: Current time phase (plenty/good/caution/warning/critical/final)
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

    total_minutes = _scan_duration_minutes
    total_seconds = total_minutes * 60
    remaining_seconds = max(0, total_seconds - elapsed_seconds)
    remaining_minutes = remaining_seconds / 60

    elapsed_percent = min(100, (elapsed_seconds / total_seconds) * 100) if total_seconds > 0 else 100
    remaining_percent = max(0, 100 - elapsed_percent)

    # Check for new notifications
    notifications = _check_and_get_notifications(remaining_minutes, total_minutes)

    # Determine phase
    if remaining_percent <= 3:
        phase = "final"
    elif remaining_percent <= 8:
        phase = "critical"
    elif remaining_percent <= 15:
        phase = "warning"
    elif remaining_percent <= 25:
        phase = "caution"
    elif remaining_percent <= 50:
        phase = "good"
    else:
        phase = "plenty"

    recommendation = _get_phase_recommendation(remaining_percent, remaining_minutes)

    result = {
        "success": True,
        "remaining_minutes": round(remaining_minutes, 2),
        "remaining_percent": round(remaining_percent, 1),
        "remaining_seconds": int(remaining_seconds),
        "elapsed_minutes": round(elapsed_minutes, 2),
        "elapsed_percent": round(elapsed_percent, 1),
        "total_minutes": total_minutes,
        "phase": phase,
        "is_critical": phase in ("critical", "final"),
        "is_warning": phase in ("warning", "critical", "final"),
        "is_caution": phase in ("caution", "warning", "critical", "final"),
        "recommendation": recommendation,
        "started_at": datetime.fromtimestamp(_scan_start_time or time.time(), tz=timezone.utc).isoformat(),
    }
    
    # Add notifications if any were triggered
    if notifications:
        result["notifications"] = notifications
        result["ATTENTION"] = f"{notifications[0]['emoji']} TIME ALERT: {notifications[0]['message']}"
    
    # Show threshold info for this timeframe
    thresholds = _calculate_thresholds(total_minutes)
    result["notification_schedule"] = {
        config["level"]: f"{config['minutes']:.1f} min ({config['percentage']}%)"
        for config in thresholds.values()
    }
    
    return result


@register_tool(sandbox_execution=False)
def get_elapsed_time(agent_state: Any) -> dict[str, Any]:
    """Get the elapsed time since scan start."""
    return get_remaining_time(agent_state)


@register_tool(sandbox_execution=False)
def is_timeframe_critical(agent_state: Any) -> dict[str, Any]:
    """
    Quick check if the timeframe is in a critical phase.

    Uses percentage-based thresholds that work for any timeframe.

    Returns:
        Dictionary with phase status and recommendations
    """
    time_info = get_remaining_time(agent_state)
    remaining_pct = time_info["remaining_percent"]
    remaining_min = time_info["remaining_minutes"]
    phase = time_info["phase"]

    return {
        "success": True,
        "phase": phase,
        "is_final": phase == "final",
        "is_critical": phase in ("critical", "final"),
        "is_warning": phase in ("warning", "critical", "final"),
        "is_caution": phase in ("caution", "warning", "critical", "final"),
        "should_wrap_up": remaining_pct <= 15,
        "should_save_state": remaining_pct <= 8,
        "remaining_minutes": remaining_min,
        "remaining_percent": remaining_pct,
        "total_minutes": time_info["total_minutes"],
        "action_required": time_info.get("ATTENTION"),
    }


@register_tool(sandbox_execution=False)
def set_scan_timeframe(
    agent_state: Any,
    duration_minutes: int,
    reset_start_time: bool = True,
) -> dict[str, Any]:
    """
    Set or reset the scan timeframe.
    
    Notifications automatically scale to the new timeframe using percentages.
    """
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

    # Calculate thresholds for this timeframe
    thresholds = _calculate_thresholds(duration_minutes)
    schedule = {
        config["level"]: f"{config['minutes']:.1f} min ({config['percentage']}% remaining)"
        for config in thresholds.values()
    }

    return {
        "success": True,
        "message": f"Timeframe set to {duration_minutes} minutes",
        "duration_minutes": duration_minutes,
        "started_at": datetime.fromtimestamp(_scan_start_time, tz=timezone.utc).isoformat(),
        "notification_schedule": schedule,
        "note": "Notifications use percentage-based thresholds that scale to any timeframe",
    }


@register_tool(sandbox_execution=False)
def should_continue_scanning(agent_state: Any) -> dict[str, Any]:
    """
    Determine if the agent should continue scanning or wrap up.

    Uses percentage-based phases that work for any timeframe:
    - Phase "plenty" (>50%): Full scanning capacity
    - Phase "good" (25-50%): Continue but plan wrap-up
    - Phase "caution" (15-25%): Prioritize remaining tests
    - Phase "warning" (8-15%): Finish current tests only
    - Phase "critical" (3-8%): Stop testing, save state
    - Phase "final" (<3%): Complete report only

    IMPORTANT: Continue scanning until timeframe is exhausted!

    Returns:
        Dictionary with continuation decision and phase-appropriate instructions
    """
    time_info = get_remaining_time(agent_state)
    remaining_pct = time_info["remaining_percent"]
    remaining_min = time_info["remaining_minutes"]
    phase = time_info["phase"]
    total_min = time_info["total_minutes"]

    should_continue = remaining_min > 0.25  # Continue until last 15 seconds
    should_start_new_tests = remaining_pct > 15
    should_save_continuation = remaining_pct <= 8

    # Phase-specific guidance
    phase_guidance = {
        "plenty": (
            f"{remaining_min:.1f} min available ({remaining_pct:.0f}% of {total_min} min).",
            "Continue comprehensive testing. Full capacity available."
        ),
        "good": (
            f"{remaining_min:.1f} min remaining ({remaining_pct:.0f}% left).",
            "Continue testing. Start planning wrap-up phase."
        ),
        "caution": (
            f"{remaining_min:.1f} min remaining ({remaining_pct:.0f}% left). Be cautious.",
            "Finish long-running scans. Focus on high-priority targets."
        ),
        "warning": (
            f"{remaining_min:.1f} min remaining ({remaining_pct:.0f}% left). Finish up.",
            "Complete current tests. Document all findings. Prepare final report."
        ),
        "critical": (
            f"{remaining_min:.1f} min remaining ({remaining_pct:.0f}% left). CRITICAL!",
            "STOP testing. File ALL reports. Save continuation state to StrixDB NOW."
        ),
        "final": (
            f"{remaining_min:.1f} min remaining ({remaining_pct:.0f}% left). FINAL!",
            "Complete report ONLY. Ensure all findings are saved. Wrap up immediately."
        ),
    }

    reason, action = phase_guidance.get(phase, (f"{remaining_min:.1f} min left.", "Continue."))

    return {
        "success": True,
        "phase": phase,
        "should_continue": should_continue,
        "should_start_new_tests": should_start_new_tests,
        "should_save_continuation": should_save_continuation,
        "remaining_minutes": remaining_min,
        "remaining_percent": remaining_pct,
        "total_minutes": total_min,
        "reason": reason,
        "action": action,
        "reminder": "Continue until timeframe exhausted! Save continuation state when in critical phase.",
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

    CALL THIS when in "critical" or "final" phase! This ensures you can continue
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
    time_info = get_remaining_time(agent_state)
    
    continuation_state = {
        "target": target,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "completed_phases": completed_phases,
        "pending_tests": pending_tests,
        "findings_summary": findings_summary,
        "notes": notes,
        "priority_followups": priority_followups or [],
        "time_info": {
            "original_duration_minutes": time_info["total_minutes"],
            "time_used_minutes": time_info["elapsed_minutes"],
            "time_remaining_minutes": time_info["remaining_minutes"],
            "phase_at_save": time_info["phase"],
        },
    }

    # Try to save to StrixDB
    try:
        from strix.tools.strixdb.strixdb_targets import _sanitize_target_slug
        from strix.tools.strixdb.strixdb_actions import strixdb_save
        
        target_slug = _sanitize_target_slug(target)
        
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


@register_tool(sandbox_execution=False)
def get_timeframe_schedule(agent_state: Any) -> dict[str, Any]:
    """
    Get the notification schedule for the current timeframe.
    
    Shows exactly when each notification will fire based on the total scan duration.
    Useful for understanding how the percentage-based system works.

    Returns:
        Dictionary with notification schedule and phase boundaries
    """
    global _scan_duration_minutes
    
    total = _scan_duration_minutes
    thresholds = _calculate_thresholds(total)
    
    schedule = []
    for config in sorted(thresholds.values(), key=lambda x: x["percentage"], reverse=True):
        schedule.append({
            "level": config["level"],
            "triggers_at": f"{config['minutes']:.1f} min remaining",
            "percentage": f"{config['percentage']}% of time left",
            "action": config["action"],
        })
    
    phases = {
        "plenty": f"> {total * 0.5:.1f} min (> 50%)",
        "good": f"{total * 0.25:.1f} - {total * 0.5:.1f} min (25-50%)",
        "caution": f"{total * 0.15:.1f} - {total * 0.25:.1f} min (15-25%)",
        "warning": f"{total * 0.08:.1f} - {total * 0.15:.1f} min (8-15%)",
        "critical": f"{total * 0.03:.1f} - {total * 0.08:.1f} min (3-8%)",
        "final": f"< {total * 0.03:.1f} min (< 3%)",
    }
    
    return {
        "success": True,
        "total_minutes": total,
        "notification_schedule": schedule,
        "phase_boundaries": phases,
        "note": "All thresholds scale automatically with any timeframe (10 min to 720 min)",
    }
