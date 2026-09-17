import os
import pytest
from datetime import date
from tiffin.service import TiffinService
from tiffin.models import SubscriptionStatus


@pytest.fixture
def service(tmp_path):
    db_file = str(tmp_path / "test_tiffin.db")
    svc = TiffinService(db_file)
    return svc


def test_subscribe_lifecycle(service):
    sub = service.subscribe(
        name="Ananya Verma",
        phone="+91 98765-11223",
        plan_id="standard_veg",
        address="B-12, Green Park",
        start_date=date(2026, 10, 1),
    )
    assert sub.customer_phone == "+919876511223"
    assert sub.plan_id == "standard_veg"
    assert sub.status == SubscriptionStatus.ACTIVE

    # Lookup customer
    lookup = service.lookup_customer("+919876511223")
    assert lookup["found"] is True
    assert lookup["customer"].name == "Ananya Verma"
    assert lookup["subscription"].status == SubscriptionStatus.ACTIVE


def test_pause_and_resume_lifecycle(service):
    phone = "9988776655"
    service.subscribe(
        name="Karan Patel",
        phone=phone,
        plan_id="special_veg",
        start_date=date(2026, 10, 1),
    )

    # Pause from Oct 12 to Oct 16
    pause_rec = service.pause(
        phone=phone,
        from_date=date(2026, 10, 12),
        to_date=date(2026, 10, 16),
        reason="Diwali festival break",
    )
    assert pause_rec.id is not None
    assert pause_rec.reason == "Diwali festival break"

    # Status check during pause: Oct 14 should be PAUSED
    st_paused = service.get_customer_status_on_date(phone, date(2026, 10, 14))
    assert st_paused["status"] == "PAUSED"
    assert st_paused["is_delivery_day"] is False
    assert st_paused["pause_reason"] == "Diwali festival break"

    # Status check after pause: Oct 19 should be ACTIVE
    st_active = service.get_customer_status_on_date(phone, date(2026, 10, 19))
    assert st_active["status"] == "ACTIVE"
    assert st_active["is_delivery_day"] is True


def test_indefinite_pause_and_explicit_resume(service):
    phone = "9123456780"
    service.subscribe(
        name="Vikram Singh",
        phone=phone,
        plan_id="standard_veg",
        start_date=date(2026, 10, 1),
    )

    # Indefinite pause starting Oct 10
    service.pause(
        phone=phone,
        from_date=date(2026, 10, 10),
        to_date=None,
        reason="Out of town until further notice",
    )

    # Status on Oct 20 should be PAUSED
    st_oct20 = service.get_customer_status_on_date(phone, date(2026, 10, 20))
    assert st_oct20["status"] == "PAUSED"

    # Resume starting Oct 21
    resumed = service.resume(phone, resume_date=date(2026, 10, 21))
    assert resumed is True

    # Status on Oct 20 was the last paused day; Oct 21 should now be ACTIVE
    st_oct20_after = service.get_customer_status_on_date(phone, date(2026, 10, 20))
    assert st_oct20_after["status"] == "PAUSED"

    st_oct21 = service.get_customer_status_on_date(phone, date(2026, 10, 21))
    assert st_oct21["status"] == "ACTIVE"


def test_overlap_pause_rejected(service):
    phone = "9000011111"
    service.subscribe(
        name="Meera Iyer",
        phone=phone,
        plan_id="standard_veg",
        start_date=date(2026, 10, 1),
    )
    service.pause(phone, from_date=date(2026, 10, 10), to_date=date(2026, 10, 15))

    # Overlapping attempt should raise ValueError
    with pytest.raises(ValueError, match="overlaps"):
        service.pause(phone, from_date=date(2026, 10, 12), to_date=date(2026, 10, 18))


def test_daily_dispatch_partitioning(service):
    # Setup two customers: one active, one paused
    service.subscribe(
        name="Active Customer",
        phone="1111111111",
        plan_id="standard_veg",
        address="101 Blue Ridge",
        start_date=date(2026, 10, 1),
    )
    service.subscribe(
        name="Paused Customer",
        phone="2222222222",
        plan_id="special_veg",
        address="202 Green Hills",
        start_date=date(2026, 10, 1),
    )

    target = date(2026, 10, 7)  # Wednesday
    service.pause(
        phone="2222222222",
        from_date=date(2026, 10, 5),
        to_date=date(2026, 10, 9),
        reason="Family trip",
    )

    dispatch = service.get_daily_dispatch(target)
    assert dispatch["is_weekday"] is True
    assert dispatch["active_count"] == 1
    assert dispatch["paused_count"] == 1
    assert dispatch["active_deliveries"][0]["name"] == "Active Customer"
    assert dispatch["paused_deliveries"][0]["name"] == "Paused Customer"
    assert dispatch["paused_deliveries"][0]["reason"] == "Family trip"
