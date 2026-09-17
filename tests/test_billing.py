import pytest
from datetime import date
from tiffin.billing import calculate_pro_rated_bill
from tiffin.models import Customer, Plan, Subscription, PauseRecord, DayStatus


@pytest.fixture
def sample_customer():
    return Customer(phone="9876543210", name="Rahul Sharma", address="Flat 402, Sunshine Apts")


@pytest.fixture
def monthly_plan():
    return Plan(id="standard_veg", name="Standard Veg", monthly_price=2200.0)


def test_full_month_delivery_matches_plan_price(sample_customer, monthly_plan):
    # October 2026 has 22 weekdays. If no pauses, customer receives all 22 days.
    # 22 * (2200 / 22) = 2200.00
    sub = Subscription(
        customer_phone=sample_customer.phone,
        plan_id=monthly_plan.id,
        start_date=date(2026, 10, 1),
    )
    bill = calculate_pro_rated_bill(
        customer=sample_customer,
        subscription=sub,
        plan=monthly_plan,
        pauses=[],
        year=2026,
        month=10,
    )

    assert bill.total_month_weekdays == 22
    assert bill.subscribed_weekdays == 22
    assert bill.paused_weekdays == 0
    assert bill.delivered_weekdays == 22
    assert bill.daily_rate == 100.0
    assert bill.total_amount == 2200.00


def test_one_week_pause_pro_rating(sample_customer, monthly_plan):
    # Paused Mon Oct 5 to Fri Oct 9 (5 weekdays)
    # Delivered = 22 - 5 = 17 days
    # Bill = 17 * 100.0 = 1700.00
    sub = Subscription(
        customer_phone=sample_customer.phone,
        plan_id=monthly_plan.id,
        start_date=date(2026, 10, 1),
    )
    pauses = [
        PauseRecord(
            customer_phone=sample_customer.phone,
            start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 9),
            reason="Visiting hometown",
        )
    ]
    bill = calculate_pro_rated_bill(
        customer=sample_customer,
        subscription=sub,
        plan=monthly_plan,
        pauses=pauses,
        year=2026,
        month=10,
    )

    assert bill.total_month_weekdays == 22
    assert bill.paused_weekdays == 5
    assert bill.delivered_weekdays == 17
    assert bill.total_amount == 1700.00


def test_weekend_overlapping_pause(sample_customer, monthly_plan):
    # Customer pauses Friday Oct 9 to Monday Oct 12 (4 calendar days, but only Fri and Mon are weekdays)
    # Total paused weekdays = 2 (not 4!)
    # Delivered = 22 - 2 = 20 weekdays
    # Bill = 20 * 100.0 = 2000.00
    sub = Subscription(
        customer_phone=sample_customer.phone,
        plan_id=monthly_plan.id,
        start_date=date(2026, 10, 1),
    )
    pauses = [
        PauseRecord(
            customer_phone=sample_customer.phone,
            start_date=date(2026, 10, 9),
            end_date=date(2026, 10, 12),
            reason="Weekend getaway",
        )
    ]
    bill = calculate_pro_rated_bill(
        customer=sample_customer,
        subscription=sub,
        plan=monthly_plan,
        pauses=pauses,
        year=2026,
        month=10,
    )

    assert bill.total_month_weekdays == 22
    assert bill.paused_weekdays == 2
    assert bill.delivered_weekdays == 20
    assert bill.total_amount == 2000.00


def test_mid_month_subscription_pro_rating(sample_customer, monthly_plan):
    # Customer subscribes starting Oct 15, 2026 (Thursday)
    # Weekdays from Oct 1 to Oct 14 are unserved (10 weekdays before start date)
    # Weekdays on/after Oct 15: 12 weekdays
    # Bill = 12 * 100.0 = 1200.00
    sub = Subscription(
        customer_phone=sample_customer.phone,
        plan_id=monthly_plan.id,
        start_date=date(2026, 10, 15),
    )
    bill = calculate_pro_rated_bill(
        customer=sample_customer,
        subscription=sub,
        plan=monthly_plan,
        pauses=[],
        year=2026,
        month=10,
    )

    assert bill.total_month_weekdays == 22
    assert bill.subscribed_weekdays == 12
    assert bill.paused_weekdays == 0
    assert bill.delivered_weekdays == 12
    assert bill.total_amount == 1200.00


def test_cross_month_pause_isolation(sample_customer, monthly_plan):
    # Pause from Oct 28, 2026 to Nov 5, 2026
    # In October (31 days):
    # Oct 28 (Wed), Oct 29 (Thu), Oct 30 (Fri) are weekdays in October -> 3 weekdays paused in Oct
    # Delivered in Oct = 22 - 3 = 19 weekdays
    # Bill = 19 * 100.0 = 1900.00
    sub = Subscription(
        customer_phone=sample_customer.phone,
        plan_id=monthly_plan.id,
        start_date=date(2026, 10, 1),
    )
    pauses = [
        PauseRecord(
            customer_phone=sample_customer.phone,
            start_date=date(2026, 10, 28),
            end_date=date(2026, 11, 5),
            reason="Extended family function",
        )
    ]
    oct_bill = calculate_pro_rated_bill(
        customer=sample_customer,
        subscription=sub,
        plan=monthly_plan,
        pauses=pauses,
        year=2026,
        month=10,
    )
    assert oct_bill.paused_weekdays == 3
    assert oct_bill.delivered_weekdays == 19
    assert oct_bill.total_amount == 1900.00


def test_entire_month_paused_results_in_zero_bill(sample_customer, monthly_plan):
    # Customer was paused the entire month of October 2026
    sub = Subscription(
        customer_phone=sample_customer.phone,
        plan_id=monthly_plan.id,
        start_date=date(2026, 10, 1),
    )
    pauses = [
        PauseRecord(
            customer_phone=sample_customer.phone,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 31),
            reason="Away for medical treatment",
        )
    ]
    bill = calculate_pro_rated_bill(
        customer=sample_customer,
        subscription=sub,
        plan=monthly_plan,
        pauses=pauses,
        year=2026,
        month=10,
    )
    assert bill.delivered_weekdays == 0
    assert bill.total_amount == 0.00


def test_leap_year_february_weekdays(sample_customer):
    # Feb 2024 (Leap year, 29 days) vs Feb 2025 (28 days)
    # Feb 2024: 29 days, starts on Thursday -> 21 weekdays.
    plan = Plan(id="test_plan", name="Test Plan", monthly_price=2100.0)
    sub = Subscription(
        customer_phone=sample_customer.phone,
        plan_id=plan.id,
        start_date=date(2024, 2, 1),
    )
    bill_2024 = calculate_pro_rated_bill(
        customer=sample_customer,
        subscription=sub,
        plan=plan,
        pauses=[],
        year=2024,
        month=2,
    )
    assert bill_2024.total_month_weekdays == 21
    assert bill_2024.delivered_weekdays == 21
    assert bill_2024.total_amount == 2100.00
