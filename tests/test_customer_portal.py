import os
import pytest
from datetime import date
from web.app import app
import web.app as web_module
from tiffin.service import TiffinService
from tiffin.models import SubscriptionStatus


@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test_portal_isolated.db")
    web_module.service = TiffinService(db_file)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as client:
        yield client


def test_customer_subscribe_get_and_post(client):
    service = web_module.service
    # GET /subscribe displays plan options
    res = client.get("/subscribe")
    assert res.status_code == 200
    assert b"Choose Your Homestyle Lunch Plan" in res.data
    assert b"Standard Vegetarian" in res.data

    # POST /subscribe registers new customer
    payload = {
        "name": "Kavita Rao",
        "phone": "9812345678",
        "plan_id": "special_veg",
        "address": "Penthouse 12, Sky Heights",
        "notes": "Less oil, no garlic",
        "start_date": "2026-10-01",
    }
    post_res = client.post("/subscribe", data=payload, follow_redirects=True)
    assert post_res.status_code == 200
    assert b"Welcome to Annapurna Tiffin, Kavita Rao!" in post_res.data
    assert b"Kavita Rao" in post_res.data
    assert b"Deluxe Vegetarian" in post_res.data

    # Verify customer and subscription created in database
    cust = service.storage.get_customer("9812345678")
    assert cust is not None
    assert cust.name == "Kavita Rao"

    sub = service.storage.get_subscription_for_customer("9812345678")
    assert sub is not None
    assert sub.plan_id == "special_veg"
    assert sub.status == SubscriptionStatus.ACTIVE


def test_customer_login_and_logout(client):
    service = web_module.service
    # Pre-subscribe a customer
    service.subscribe(
        name="Manish Malhotra",
        phone="9823456789",
        plan_id="standard_veg",
        address="Flat 204",
        start_date=date(2026, 10, 1),
    )

    # 1. Unknown phone number fails gracefully with subscription prompt
    fail_res = client.post("/customer/login", data={"phone": "9999999999"}, follow_redirects=True)
    assert fail_res.status_code == 200
    assert b"No active subscription found for phone" in fail_res.data
    assert b"Subscribe to a Meal Plan" in fail_res.data

    # 2. Registered phone number succeeds
    login_res = client.post("/customer/login", data={"phone": "9823456789"}, follow_redirects=True)
    assert login_res.status_code == 200
    assert b"Welcome back, Manish Malhotra!" in login_res.data
    assert b"My Tiffin Dashboard" in login_res.data

    # 3. Customer Logout
    logout_res = client.get("/customer/logout", follow_redirects=True)
    assert logout_res.status_code == 200
    assert b"You have been logged out of your customer portal." in logout_res.data

    # 4. Accessing dashboard when logged out redirects to customer login
    dash_res = client.get("/customer/dashboard", follow_redirects=True)
    assert dash_res.status_code == 200
    assert b"Please enter your phone number to access your customer dashboard." in dash_res.data
    assert b"Customer Portal Login" in dash_res.data


def test_customer_self_service_pause_and_resume(client):
    service = web_module.service
    # Subscribe customer
    service.subscribe(
        name="Rohan Mehra",
        phone="9834567890",
        plan_id="standard_veg",
        address="Office 5B, DLF Cyber City",
        start_date=date(2026, 10, 1),
    )

    # Login customer
    client.post("/customer/login", data={"phone": "9834567890"})

    # Schedule pause from Oct 5 to Oct 9
    pause_payload = {
        "from_date": "2026-10-05",
        "to_date": "2026-10-09",
        "reason": "Attending Bangalore conference",
    }
    pause_res = client.post("/customer/pause", data=pause_payload, follow_redirects=True)
    assert pause_res.status_code == 200
    assert b"Your pause has been scheduled. You will NOT be charged for paused weekdays!" in pause_res.data

    # Verify pause was created
    pauses = service.storage.get_pauses_for_customer("9834567890")
    assert len(pauses) == 1
    assert pauses[0].reason == "Attending Bangalore conference"

    # Resume delivery
    resume_payload = {
        "resume_date": "2026-10-10",
    }
    resume_res = client.post("/customer/resume", data=resume_payload, follow_redirects=True)
    assert resume_res.status_code == 200
    assert b"Your lunch delivery has been resumed successfully!" in resume_res.data
