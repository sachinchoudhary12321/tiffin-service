import pytest
from datetime import date
from tiffin.calendar_utils import (
    is_weekday,
    get_month_weekdays,
    get_weekdays_in_range,
    is_date_in_interval,
    parse_date,
    format_date,
)


def test_is_weekday():
    # 2026-10-05 is Monday, 2026-10-09 is Friday, 2026-10-10 is Saturday, 2026-10-11 is Sunday
    assert is_weekday(date(2026, 10, 5)) is True
    assert is_weekday(date(2026, 10, 6)) is True
    assert is_weekday(date(2026, 10, 7)) is True
    assert is_weekday(date(2026, 10, 8)) is True
    assert is_weekday(date(2026, 10, 9)) is True
    assert is_weekday(date(2026, 10, 10)) is False
    assert is_weekday(date(2026, 10, 11)) is False


def test_get_month_weekdays_october_2026():
    # October 2026 has 31 days. Starts on Thursday (Oct 1).
    weekdays = get_month_weekdays(2026, 10)
    # Total days: 31. Saturdays: 3, 10, 17, 24, 31 (5 Saturdays). Sundays: 4, 11, 18, 25 (4 Sundays).
    # 31 - 9 weekend days = 22 weekdays.
    assert len(weekdays) == 22
    assert all(is_weekday(d) for d in weekdays)


def test_get_month_weekdays_with_holidays():
    holidays = {date(2026, 10, 2), date(2026, 10, 20)}  # Gandhi Jayanti, etc.
    weekdays = get_month_weekdays(2026, 10, holidays=holidays)
    assert len(weekdays) == 20
    assert date(2026, 10, 2) not in weekdays
    assert date(2026, 10, 20) not in weekdays


def test_weekdays_in_range():
    # Friday to Monday (Oct 9 to Oct 12, 2026) -> Oct 9 (Fri) and Oct 12 (Mon)
    range_weekdays = get_weekdays_in_range(date(2026, 10, 9), date(2026, 10, 12))
    assert range_weekdays == [date(2026, 10, 9), date(2026, 10, 12)]


def test_is_date_in_interval():
    start = date(2026, 10, 5)
    end = date(2026, 10, 9)
    assert is_date_in_interval(date(2026, 10, 4), start, end) is False
    assert is_date_in_interval(date(2026, 10, 5), start, end) is True
    assert is_date_in_interval(date(2026, 10, 7), start, end) is True
    assert is_date_in_interval(date(2026, 10, 9), start, end) is True
    assert is_date_in_interval(date(2026, 10, 10), start, end) is False

    # Indefinite interval
    assert is_date_in_interval(date(2026, 10, 25), start, None) is True
