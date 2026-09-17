import json
import pytest
from datetime import date
from web.app import app
import web.app as web_module
from tiffin.chatbot import TiffinChatbot
from tiffin.service import TiffinService


@pytest.fixture
def client(tmp_path):
    test_db = str(tmp_path / "test_api_isolated.db")
    web_module.service = TiffinService(test_db)
    web_module.chatbot = TiffinChatbot(web_module.service)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_landing_page_mandatory_sections(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    assert "What is Annapurna Tiffin?" in html
    assert "Target Audience" in html
    assert "How It Helps" in html
    assert "Three Features We Would Build Next" in html
    assert "WhatsApp AI Chatbot" in html
    assert "Automated UPI Payment Links" in html
    assert "Delivery Driver Dynamic Route Clustering" in html


def test_login_and_register_web_views(client):
    r_login = client.get("/login")
    assert r_login.status_code == 200
    assert "Owner Login" in r_login.data.decode("utf-8")

    r_reg = client.get("/register")
    assert r_reg.status_code == 200
    assert "Create Owner Account" in r_reg.data.decode("utf-8")


def test_api_auth_lifecycle(client):
    reg_payload = {
        "username": "chef_ramesh",
        "password": "rameshpassword",
        "email": "ramesh@tiffin.in",
    }
    r_reg = client.post("/api/auth/register", json=reg_payload)
    assert r_reg.status_code == 201
    assert r_reg.json["success"] is True

    login_payload = {
        "username": "chef_ramesh",
        "password": "rameshpassword",
    }
    r_login = client.post("/api/auth/login", json=login_payload)
    assert r_login.status_code == 200
    assert r_login.json["success"] is True

    r_me = client.get("/api/auth/me")
    assert r_me.status_code == 200
    assert r_me.json["user"]["username"] == "chef_ramesh"

    r_out = client.post("/api/auth/logout")
    assert r_out.status_code == 200

    r_me_after = client.get("/api/auth/me")
    assert r_me_after.status_code == 401


def test_api_plans_endpoint(client):
    res = client.get("/api/plans")
    assert res.status_code == 200
    assert res.json["success"] is True
    plan_ids = [p["id"] for p in res.json["plans"]]
    assert "standard_veg" in plan_ids


def test_api_subscribe_pause_resume_and_bill(client):
    phone = "9988001122"
    sub_data = {
        "name": "Deepak Joshi",
        "phone": phone,
        "plan_id": "standard_veg",
        "address": "B-201, Green Heights",
        "start_date": "2026-10-01",
    }
    r_sub = client.post("/api/subscriptions", json=sub_data)
    assert r_sub.status_code == 201
    assert r_sub.json["success"] is True

    r_dos = client.get(f"/api/customers/{phone}?date=2026-10-01")
    assert r_dos.status_code == 200
    assert r_dos.json["customer"]["name"] == "Deepak Joshi"

    pause_data = {
        "phone": phone,
        "from_date": "2026-10-05",
        "to_date": "2026-10-09",
        "reason": "Out of town",
    }
    r_pause = client.post("/api/pauses", json=pause_data)
    assert r_pause.status_code == 201

    r_disp = client.get("/api/dispatch?date=2026-10-07")
    assert r_disp.status_code == 200
    assert r_disp.json["paused_count"] >= 1

    r_bill = client.get(f"/api/bills/{phone}?month=2026-10")
    assert r_bill.status_code == 200
    bill = r_bill.json["bill"]
    assert bill["total_month_weekdays"] == 22
    assert bill["paused_weekdays"] == 5
    assert bill["delivered_weekdays"] == 17
    assert len(bill["days_breakdown"]) == 31


def test_api_customers_search_pagination_sorting(client):
    # Subscribe 2 customers
    client.post("/api/subscriptions", json={
        "name": "Arjun Das", "phone": "9811111111", "plan_id": "standard_veg"
    })
    client.post("/api/subscriptions", json={
        "name": "Bhavna Rao", "phone": "9822222222", "plan_id": "special_veg"
    })

    res = client.get("/api/customers?query=Arjun&page=1&per_page=5&sort_by=name&order=asc")
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert len(data["customers"]) == 1
    assert data["customers"][0]["name"] == "Arjun Das"


def test_api_bills_summary_pagination(client):
    client.post("/api/subscriptions", json={
        "name": "Karan Johar", "phone": "9833333333", "plan_id": "standard_veg", "start_date": "2026-10-01"
    })
    res = client.get("/api/bills?month=2026-10&page=1&per_page=5&sort_by=total_amount&order=desc")
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert "bills" in data
    assert "grand_total" in data


def test_whatsapp_link_generation():
    from tiffin.models import Bill, DayStatus
    b = Bill(
        customer_phone="9876543210",
        customer_name="Sunita Rao",
        plan_id="standard_veg",
        plan_name="Standard Vegetarian",
        plan_monthly_price=3000.0,
        billing_year=2026,
        billing_month=10,
        month_name="October",
        total_month_weekdays=22,
        subscribed_weekdays=22,
        paused_weekdays=5,
        holiday_weekdays=0,
        delivered_weekdays=17,
        daily_rate=136.3636,
        total_amount=2318.18,
    )
    link = web_module.service.generate_whatsapp_message(b)
    assert link.startswith("https://wa.me/919876543210?text=")
    assert "Annapurna" in link
    assert "2318.18" in link


def test_csv_exports(client):
    # Test bills CSV export
    r_csv = client.get("/export/bills.csv?month=2026-10")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers.get("Content-Type", "")
    assert "Customer Name,Phone,Plan" in r_csv.data.decode("utf-8")

    # Test dispatch CSV export
    r_disp_csv = client.get("/export/dispatch.csv?date=2026-10-07")
    assert r_disp_csv.status_code == 200
    assert "text/csv" in r_disp_csv.headers.get("Content-Type", "")
    assert "Delivery Status,Customer Name,Phone" in r_disp_csv.data.decode("utf-8")


def test_customer_self_service_portal(client):
    client.post("/api/subscriptions", json={
        "name": "Manish Malhotra", "phone": "9844444444", "plan_id": "standard_veg", "start_date": "2026-10-01"
    })
    res = client.get("/my-bill?phone=9844444444&month=2026-10")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Customer Self-Service Bill Portal" in html
    assert "Manish Malhotra" in html
    assert "Verified Bill" in html

