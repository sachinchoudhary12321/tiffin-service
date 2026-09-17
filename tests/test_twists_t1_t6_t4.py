from datetime import date
import pytest
from tiffin.calendar_utils import parse_flexible_date
from tiffin.service import TiffinService
from web.app import app
import web.app as web_module


@pytest.fixture
def service_env(tmp_path):
    test_db = str(tmp_path / "test_twists.db")
    svc = TiffinService(test_db)
    web_module.service = svc
    app.config["TESTING"] = True
    return svc


# =============================================================================
# LEVEL 1 — T1 (integrate): /clock and /outbox Notification Service
# =============================================================================

def test_level1_clock_and_outbox_workflow(service_env):
    # Customer 1: Active
    service_env.subscribe(
        name="Sunita Rao",
        phone="9811111111",
        plan_id="standard_veg",
        start_date=date(2026, 10, 1),
    )
    # Customer 2: Paused on Wednesday 2026-10-07
    service_env.subscribe(
        name="Vikram Seth",
        phone="9822222222",
        plan_id="special_veg",
        start_date=date(2026, 10, 1),
    )
    service_env.pause(
        phone="9822222222",
        from_date=date(2026, 10, 5),
        to_date=date(2026, 10, 9),
        reason="Festival travel",
    )

    with app.test_client() as client:
        # Clear outbox
        client.delete("/outbox")

        # 1. Sunday 2026-10-04: Weekend -> 0 notifications
        r_sun = client.post("/clock", json={"date": "2026-10-04"})
        assert r_sun.status_code == 200
        assert r_sun.json["dispatched_count"] == 0

        # 2. Wednesday 2026-10-07: Weekday -> Only Sunita Rao due delivery, Vikram is paused
        r_wed = client.post("/clock", json={"date": "2026-10-07"})
        assert r_wed.status_code == 200
        assert r_wed.json["dispatched_count"] == 1
        assert r_wed.json["outbox"][0]["recipient"] == "9811111111"
        assert "Sunita Rao" in r_wed.json["outbox"][0]["customer_name"]

        # 3. Verify GET /outbox
        r_outbox = client.get("/outbox")
        assert r_outbox.status_code == 200
        assert r_outbox.json["count"] >= 1
        recipients = [item["recipient"] for item in r_outbox.json["outbox"]]
        assert "9811111111" in recipients
        assert "9822222222" not in recipients  # Paused customer must NOT receive delivery notification

        # 4. DELETE /outbox
        r_del = client.delete("/outbox")
        assert r_del.status_code == 200
        r_empty = client.get("/outbox")
        assert r_empty.json["count"] == 0


# =============================================================================
# LEVEL 2 — T6 (lifecycle): Mid-Cycle Subscription Transfer with Split Billing
# =============================================================================

def test_level2_mid_cycle_subscription_transfer(service_env):
    # October 2026: 22 total weekdays.
    # Plan: Standard Veg (Rs. 3000 / month) -> Daily rate = 3000 / 22 = Rs. 136.3636/day.
    service_env.subscribe(
        name="Anand Verma",
        phone="9833333333",
        plan_id="standard_veg",
        start_date=date(2026, 10, 1),
    )

    # Transfer mid-cycle on October 15, 2026 (Thursday) to Neha Gupta
    # Anand serves: Oct 1 to Oct 14 (10 weekdays: Oct 1, 2, 5, 6, 7, 8, 9, 12, 13, 14)
    # Neha serves: Oct 15 to Oct 31 (12 weekdays: Oct 15, 16, 19, 20, 21, 22, 23, 26, 27, 28, 29, 30)
    with app.test_client() as client:
        payload = {
            "from_phone": "9833333333",
            "to_phone": "9844444444",
            "to_name": "Neha Gupta",
            "effective_date": "2026-10-15",
            "to_address": "Flat 801, Lotus Towers",
            "notes": "Transfer mid-month",
        }
        r_xfer = client.post("/api/subscriptions/transfer", json=payload)
        assert r_xfer.status_code == 200
        assert r_xfer.json["success"] is True

        # Generate Bill for Anand (Sender)
        bill_anand = service_env.generate_bill("9833333333", 2026, 10)
        assert bill_anand.delivered_weekdays == 10
        assert bill_anand.total_amount == 1363.64

        # Generate Bill for Neha (Transferee)
        bill_neha = service_env.generate_bill("9844444444", 2026, 10)
        assert bill_neha.delivered_weekdays == 12
        assert bill_neha.total_amount == 1636.36

        # Mathematical Split Verification: Sum of split bills equals total plan price
        assert round(bill_anand.total_amount + bill_neha.total_amount, 2) == 3000.00
        assert bill_anand.delivered_weekdays + bill_neha.delivered_weekdays == 22


# =============================================================================
# LEVEL 3 — T4 (messy data): Ingest Messy Customer List
# =============================================================================

def test_level3_messy_customer_import(service_env):
    # Seed an existing subscriber to test database duplicate detection
    service_env.subscribe(
        name="Existing User",
        phone="9855555555",
        plan_id="standard_veg",
        start_date=date(2026, 10, 1),
    )

    messy_batch = [
        # 1. Clean ISO record -> IMPORTED
        {
            "name": "Kavita Shah",
            "phone": "9866666666",
            "start_date": "2026-10-01",
            "plan_id": "special_veg",
            "address": "B-201, Green Acres",
        },
        # 2. Messy formatted phone (+91 and hyphens) and Indian date DD/MM/YYYY -> IMPORTED
        {
            "name": "Deepak Joshi",
            "phone": "+91 98777-77777",
            "start_date": "15/10/2026",
            "plan_id": "standard_veg",
            "address": "A-12, Sector 4",
        },
        # 3. Duplicate phone within batch -> DEDUPED
        {
            "name": "Deepak J (Duplicate)",
            "phone": "9877777777",
            "start_date": "2026-10-15",
            "plan_id": "standard_veg",
        },
        # 4. Phone already exists in database with active subscription -> DEDUPED
        {
            "name": "Existing Duplicate",
            "phone": "9855555555",
            "start_date": "2026-10-01",
        },
        # 5. Missing customer name (blank) -> REJECTED
        {
            "name": "",
            "phone": "9888888888",
            "start_date": "2026-10-01",
        },
        # 6. Invalid phone (< 8 digits) -> REJECTED
        {
            "name": "Bad Phone User",
            "phone": "12345",
            "start_date": "2026-10-01",
        },
        # 7. Unparseable corrupted date format -> REJECTED
        {
            "name": "Bad Date User",
            "phone": "9899999999",
            "start_date": "invalid-non-date",
        },
    ]

    with app.test_client() as client:
        res = client.post("/api/import", json={"customers": messy_batch})
        assert res.status_code == 200
        data = res.json

        assert data["success"] is True
        summary = data["summary"]
        assert summary["total_rows"] == 7
        assert summary["imported_count"] == 2
        assert summary["deduped_count"] == 2
        assert summary["rejected_count"] == 3

        # Verify imported customers exist in database
        imported_phones = [item["phone"] for item in data["imported"]]
        assert any("9866666666" in p for p in imported_phones)
        assert any("9877777777" in p for p in imported_phones)

        # Verify deduped reasons
        assert len(data["deduped"]) == 2
        # Verify rejected reasons
        assert len(data["rejected"]) == 3
        reasons = [r["reason"] for r in data["rejected"]]
        assert any("Missing customer name" in r for r in reasons)
        assert any("less than 8" in r for r in reasons)
        assert any("Unparseable date" in r for r in reasons)


def test_flexible_date_parser():
    # Test all variations handled by parse_flexible_date
    assert parse_flexible_date("2026-10-01") == date(2026, 10, 1)
    assert parse_flexible_date("01/10/2026") == date(2026, 10, 1)
    assert parse_flexible_date("10/25/2026") == date(2026, 10, 25)
    assert parse_flexible_date("01-10-2026") == date(2026, 10, 1)
    assert parse_flexible_date("October 1, 2026") == date(2026, 10, 1)
    assert parse_flexible_date("Oct 1, 2026") == date(2026, 10, 1)
    assert parse_flexible_date("1 Oct 2026") == date(2026, 10, 1)
    assert parse_flexible_date("2026-10-01T08:30:00") == date(2026, 10, 1)
    assert parse_flexible_date("invalid") is None
    assert parse_flexible_date("") is None
    assert parse_flexible_date(None) is None
