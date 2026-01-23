import os
import time
from typing import Optional

class TimeKeeper:
    """
    Utility for tracking session deadlines and managing agent pacing.
    Respects the timeframe provided via environment variables from the workflow.
    """
    def __init__(self):
        self.start_time = float(os.getenv("STRIX_SCAN_START_TIME", time.time()))
        duration_minutes = int(os.getenv("STRIX_SCAN_DURATION_MINUTES", "60"))
        self.duration_seconds = duration_minutes * 60
        self.end_time = self.start_time + self.duration_seconds
        
    def get_remaining_seconds(self) -> float:
        """Returns the number of seconds remaining until the deadline."""
        return max(0, self.end_time - time.time())
    
    def get_remaining_minutes(self) -> float:
        """Returns the number of minutes remaining until the deadline."""
        return self.get_remaining_seconds() / 60
    
    def get_elapsed_percentage(self) -> float:
        """Returns the percentage of the timeframe that has elapsed (0.0 to 1.0)."""
        elapsed = time.time() - self.start_time
        return min(1.0, elapsed / self.duration_seconds) if self.duration_seconds > 0 else 1.0
    
    def calculate_pacing_delay(self, current_action_count: int, total_estimated_actions: int = 100) -> float:
        """
        Calculates a dynamic delay to ensure the scan lasts the full timeframe.
        Useful for 'Depth' mode where we want to pace the agent.
        """
        remaining = self.get_remaining_seconds()
        if remaining <= 0:
            return 0
        
        # Simple pacing: distribute remaining time over estimated remaining actions
        remaining_actions = max(1, total_estimated_actions - current_action_count)
        return min(60, remaining / (remaining_actions * 2)) # Cap delay at 60s per step
    
    def is_time_up(self) -> bool:
        """Checks if the timeframe has been exhausted."""
        return self.get_remaining_seconds() <= 0
