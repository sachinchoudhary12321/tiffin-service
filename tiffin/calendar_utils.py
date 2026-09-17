"""
Calendar utilities for weekday-only tiffin delivery service.
Handles weekday detection, month weekday enumeration, and date range calculations.
"""

from __future__ import annotations
import calendar
from datetime import date, datetime, timedelta
from typing import List, Optional, Set


def parse_date(d: str | date) -> date:
    """Parse date from string YYYY-MM-DD or return date object."""
    if isinstance(d, date):
        return d
    return datetime.strptime(d.strip(), "%Y-%m-%d").date()


def parse_flexible_date(d: str | date | None) -> Optional[date]:
    """
    Parse a date from various formats commonly found in messy spreadsheets.
    Supports:
      - 2026-10-01, 2026/10/01, 2026.10.01
      - 01/10/2026, 01-10-2026, 01.10.2026
      - 10/01/2026, 10-01-2026
      - October 1, 2026, Oct 1, 2026, 1 Oct 2026
      - ISO datetime strings (2026-10-01T12:00:00)
    Returns None if unparseable.
    """
    if d is None:
        return None
    if isinstance(d, date):
        return d
    if isinstance(d, datetime):
        return d.date()

    cleaned = str(d).strip()
    if not cleaned:
        return None

    # Try ISO fromisoformat first
    try:
        # Handle ISO strings with T
        if "T" in cleaned:
            return datetime.fromisoformat(cleaned).date()
    except Exception:
        pass

    # Check for smart disambiguation when year is at the end (e.g. 10/25/2026 vs 25/10/2026)
    import re
    parts = re.split(r"[/.-]", cleaned)
    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and len(parts[2]) == 4:
        v0, v1, year_val = int(parts[0]), int(parts[1]), int(parts[2])
        if v0 > 12 and 1 <= v1 <= 12:
            try:
                return date(year_val, v1, v0)
            except ValueError:
                pass
        elif v1 > 12 and 1 <= v0 <= 12:
            try:
                return date(year_val, v0, v1)
            except ValueError:
                pass

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    return None


def format_date(d: date) -> str:
    """Format date as YYYY-MM-DD."""
    return d.strftime("%Y-%m-%d")


def is_weekday(d: date) -> bool:
    """Return True if date is Monday through Friday (0 = Monday, 4 = Friday)."""
    return d.weekday() < 5


def get_month_weekdays(year: int, month: int, holidays: Optional[Set[date]] = None) -> List[date]:
    """
    Get all billable weekdays in a given year and month.
    Excludes weekends (Saturday, Sunday) and optional kitchen holidays.
    """
    holidays = holidays or set()
    num_days = calendar.monthrange(year, month)[1]
    weekdays: List[date] = []
    for day in range(1, num_days + 1):
        d = date(year, month, day)
        if is_weekday(d) and d not in holidays:
            weekdays.append(d)
    return weekdays


def get_weekdays_in_range(start: date, end: date, holidays: Optional[Set[date]] = None) -> List[date]:
    """Get all weekdays within inclusive [start, end] range."""
    if start > end:
        return []
    holidays = holidays or set()
    result: List[date] = []
    curr = start
    while curr <= end:
        if is_weekday(curr) and curr not in holidays:
            result.append(curr)
        curr += timedelta(days=1)
    return result


def is_date_in_interval(target: date, interval_start: date, interval_end: Optional[date]) -> bool:
    """
    Check if target date falls within [interval_start, interval_end].
    If interval_end is None, it represents an indefinite interval continuing indefinitely.
    """
    if target < interval_start:
        return False
    if interval_end is not None and target > interval_end:
        return False
    return True
