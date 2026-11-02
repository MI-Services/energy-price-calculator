"""Shared helpers for percentage-based window calculations (floor semantics).

Both the current-day binary sensors (TopCheapestSensor) and the
 tomorrow sensors (CheapestHoursTomorrowSensor) use the same floor
 semantics: rank * 100 <= pct * intervals. This module centralizes
 that logic to avoid duplication and ensure consistency.

Floor semantics means a sensor is never ON for more than X% of the
 day's intervals: 10% of 24 hours = rank 1-2, 10% of 96 quarter-hours
 = rank 1-9.
"""
from typing import List, Optional

from .api_client import HourData


def is_in_cheapest_window(rank: int, pct: int, interval_count: int) -> bool:
    """Check if a rank falls within the cheapest X% window (floor semantics).
    
    Args:
        rank: The rank of the hour/interval (1 = cheapest, higher = more expensive)
        pct: The percentage threshold (10, 20, ..., 90)
        interval_count: Total number of intervals in the day
        
    Returns:
        True if the rank is within the cheapest X% of intervals.
        
    Example:
        For 24 intervals (hourly prices):
        - 10% window: ranks 1-2 (0.10 * 24 = 2.4, floor = 2)
        - 20% window: ranks 1-4 (0.20 * 24 = 4.8, floor = 4)
    """
    return interval_count > 0 and (rank * 100) <= pct * interval_count


def get_cheapest_window(
    hours: Optional[List[HourData]], pct: int
) -> List[HourData]:
    """Get all hours within the cheapest X% window, ordered by start time.
    
    Args:
        hours: List of HourData objects for the day
        pct: The percentage threshold (10, 20, ..., 90)
        
    Returns:
        Sorted list of HourData objects in the cheapest X% window,
        or empty list if no data available.
    """
    if not hours:
        return []
    interval_count = len(hours)
    return sorted(
        (h for h in hours if is_in_cheapest_window(h.rank, pct, interval_count)),
        key=lambda h: h.starts_at,
    )
