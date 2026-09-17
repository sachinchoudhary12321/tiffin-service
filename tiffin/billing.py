"""
Billing engine for calculating pro-rated monthly bills.
Guarantees customers are only charged for weekdays actually served.
"""

from __future__ import annotations
import calendar
from datetime import date
from typing import List, Optional, Set

from .calendar_utils import get_month_weekdays, is_weekday
from .models import Bill, Customer, DayStatus, ItemizedDay, PauseRecord, Plan, Subscription


def calculate_pro_rated_bill(
    customer: Customer,
    subscription: Subscription,
    plan: Plan,
    pauses: List[PauseRecord],
    year: int,
    month: int,
    kitchen_holidays: Optional[Set[date]] = None,
) -> Bill:
    """
    Calculate the exact pro-rated bill for a customer for a specific year and month.
    
    Formula:
      Daily Rate = Plan Monthly Price / Total Billable Weekdays in Month
      Total Bill = round(Delivered Weekdays * Daily Rate, 2)
    """
    kitchen_holidays = kitchen_holidays or set()
    num_days = calendar.monthrange(year, month)[1]
    month_name = calendar.month_name[month]

    days_breakdown: List[ItemizedDay] = []
    
    total_month_weekdays = 0
    subscribed_weekdays = 0
    paused_weekdays = 0
    holiday_weekdays = 0
    delivered_weekdays = 0

    for day in range(1, num_days + 1):
        curr_date = date(year, month, day)
        day_name = curr_date.strftime("%A")

        if not is_weekday(curr_date):
            # Weekends are not delivery days
            days_breakdown.append(
                ItemizedDay(
                    date=curr_date,
                    day_name=day_name,
                    status=DayStatus.WEEKEND,
                    billable=False,
                    note="Weekend - no delivery",
                )
            )
            continue

        # Check kitchen holiday
        if curr_date in kitchen_holidays:
            holiday_weekdays += 1
            days_breakdown.append(
                ItemizedDay(
                    date=curr_date,
                    day_name=day_name,
                    status=DayStatus.HOLIDAY,
                    billable=False,
                    note="Kitchen holiday",
                )
            )
            continue

        total_month_weekdays += 1

        # Check subscription active window
        if curr_date < subscription.start_date:
            days_breakdown.append(
                ItemizedDay(
                    date=curr_date,
                    day_name=day_name,
                    status=DayStatus.NOT_SUBSCRIBED,
                    billable=False,
                    note="Before subscription start date",
                )
            )
            continue

        if subscription.end_date is not None and curr_date > subscription.end_date:
            days_breakdown.append(
                ItemizedDay(
                    date=curr_date,
                    day_name=day_name,
                    status=DayStatus.NOT_SUBSCRIBED,
                    billable=False,
                    note="After subscription end date",
                )
            )
            continue

        subscribed_weekdays += 1

        # Check if paused on this date
        matching_pause = None
        for p in pauses:
            if p.is_active_on(curr_date):
                matching_pause = p
                break

        if matching_pause is not None:
            paused_weekdays += 1
            reason_str = f"Paused: {matching_pause.reason}" if matching_pause.reason else "Paused"
            days_breakdown.append(
                ItemizedDay(
                    date=curr_date,
                    day_name=day_name,
                    status=DayStatus.PAUSED,
                    billable=False,
                    note=reason_str,
                )
            )
        else:
            delivered_weekdays += 1
            days_breakdown.append(
                ItemizedDay(
                    date=curr_date,
                    day_name=day_name,
                    status=DayStatus.DELIVERED,
                    billable=True,
                    note="Lunch delivered",
                )
            )

    # Compute pro-ration
    if total_month_weekdays > 0:
        daily_rate = plan.monthly_price / total_month_weekdays
    else:
        daily_rate = 0.0

    total_amount = round(delivered_weekdays * daily_rate, 2)

    return Bill(
        customer_phone=customer.phone,
        customer_name=customer.name,
        plan_id=plan.id,
        plan_name=plan.name,
        plan_monthly_price=plan.monthly_price,
        billing_year=year,
        billing_month=month,
        month_name=month_name,
        total_month_weekdays=total_month_weekdays,
        subscribed_weekdays=subscribed_weekdays,
        paused_weekdays=paused_weekdays,
        holiday_weekdays=holiday_weekdays,
        delivered_weekdays=delivered_weekdays,
        daily_rate=round(daily_rate, 4),
        total_amount=total_amount,
        days_breakdown=days_breakdown,
    )
