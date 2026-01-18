"""Timeframe Tracking Module - Scan duration management with notifications."""

from strix.tools.timeframe.timeframe_actions import (
    get_elapsed_time,
    get_remaining_time,
    is_timeframe_critical,
    load_continuation_state,
    save_scan_continuation_state,
    set_scan_timeframe,
    should_continue_scanning,
)

__all__ = [
    "get_elapsed_time",
    "get_remaining_time",
    "is_timeframe_critical",
    "load_continuation_state",
    "save_scan_continuation_state",
    "set_scan_timeframe",
    "should_continue_scanning",
]
