"""
Domain data models for tiffin delivery service.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional


class DayStatus(str, Enum):
    DELIVERED = "DELIVERED"
    PAUSED = "PAUSED"
    NOT_SUBSCRIBED = "NOT_SUBSCRIBED"
    HOLIDAY = "HOLIDAY"
    WEEKEND = "WEEKEND"


class SubscriptionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


@dataclass
class Kitchen:
    id: str
    name: str
    cuisine: str
    location: str
    rating: float = 4.8
    fssai_license: str = ""
    phone: str = ""
    description: str = ""
    specialty: str = ""


@dataclass
class Plan:
    id: str
    name: str
    monthly_price: float
    description: str = ""
    kitchen_id: str = "annapurna"
    kitchen_name: str = "Annapurna Homestyle Kitchen"


@dataclass
class Customer:
    phone: str
    name: str
    address: str = ""
    notes: str = ""
    created_at: str = ""


@dataclass
class Subscription:
    customer_phone: str
    plan_id: str
    start_date: date
    end_date: Optional[date] = None
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    id: Optional[int] = None


@dataclass
class PauseRecord:
    customer_phone: str
    start_date: date
    end_date: Optional[date] = None  # None indicates indefinite pause
    reason: str = ""
    created_at: str = ""
    id: Optional[int] = None

    def is_active_on(self, target: date) -> bool:
        """Check if pause is in effect on target date."""
        if target < self.start_date:
            return False
        if self.end_date is not None and target > self.end_date:
            return False
        return True


@dataclass
class User:
    username: str
    password_hash: str
    email: str = ""
    role: str = "owner"
    created_at: str = ""
    id: Optional[int] = None



@dataclass
class ItemizedDay:
    date: date
    day_name: str
    status: DayStatus
    billable: bool
    note: str = ""


@dataclass
class Bill:
    customer_phone: str
    customer_name: str
    plan_id: str
    plan_name: str
    plan_monthly_price: float
    billing_year: int
    billing_month: int
    month_name: str
    total_month_weekdays: int
    subscribed_weekdays: int
    paused_weekdays: int
    holiday_weekdays: int
    delivered_weekdays: int
    daily_rate: float
    total_amount: float
    days_breakdown: List[ItemizedDay] = field(default_factory=list)
