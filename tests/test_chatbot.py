from datetime import date
import pytest
from tiffin.chatbot import TiffinChatbot
from tiffin.service import TiffinService
from web.app import app
import web.app as web_module


@pytest.fixture
def chatbot_service(tmp_path):
    test_db = str(tmp_path / "test_chatbot.db")
    service = TiffinService(test_db)
    # Seed a test customer
    service.subscribe(
        name="Ramesh Kumar",
        phone="9876543210",
        plan_id="standard_veg",
        address="Flat 402, Sunshine Heights, Mumbai",
        notes="Medium spice",
        start_date=date(2026, 10, 1),
    )
    return service


@pytest.fixture
def chatbot(chatbot_service):
    return TiffinChatbot(chatbot_service)


def test_chatbot_plans_inquiry(chatbot):
    res = chatbot.answer_query("What are your meal schemes and how much do they cost?")
    assert res["intent"] == "plans_inquiry"
    assert "Standard Veg" in res["reply"]
    assert "3000" in res["reply"]
    assert "3800" in res["reply"]
    assert "4200" in res["reply"]
    assert len(res["reasoning"]) > 0
    assert len(res["grounded_facts"]) >= 3


def test_chatbot_proration_explanation(chatbot):
    res = chatbot.answer_query("How is my pro-rated bill calculated if I pause?")
    assert res["intent"] == "proration_explanation"
    assert "Daily Rate" in res["reply"]
    assert "Working Weekdays" in res["reply"]
    assert len(res["reasoning"]) > 0


def test_chatbot_pause_policy(chatbot):
    res = chatbot.answer_query("What happens if I pause from Friday to Monday?")
    assert res["intent"] == "pause_policy"
    assert "Friday and Monday" in res["reply"] or "2 delivery weekdays" in res["reply"]
    assert "Saturdays and Sundays are never charged" in res["reply"]
    assert len(res["reasoning"]) > 0


def test_chatbot_scenario_simulation(chatbot):
    res = chatbot.answer_query("If I pause for 5 days on standard veg, what will I pay?")
    assert res["intent"] == "simulation"
    assert "2,318.18" in res["reply"] or "2318.18" in res["reply"]
    assert "17 days" in res["reply"] or "17" in res["reply"]
    assert len(res["reasoning"]) >= 3


def test_chatbot_customer_lookup_found(chatbot):
    res = chatbot.answer_query("Check my bill and status for 9876543210")
    assert res["intent"] == "customer_lookup_success"
    assert "Ramesh Kumar" in res["reply"]
    assert "Standard Veg" in res["reply"]
    assert len(res["grounded_facts"]) > 0


def test_chatbot_customer_lookup_not_found(chatbot):
    res = chatbot.answer_query("What is the bill for 1112223333?")
    assert res["intent"] == "customer_lookup_not_found"
    assert "could not find a customer" in res["reply"]
    assert "1112223333" in res["reply"]


def test_chatbot_fallback_zero_hallucination(chatbot):
    res = chatbot.answer_query("Can you tell me about the weather on Mars?")
    assert res["intent"] == "general_help"
    assert "Annapurna Tiffin AI Assistant" in res["reply"]
    assert "zero hallucination" in res["reply"].lower()


def test_api_chat_and_assistant_page(tmp_path):
    test_db = str(tmp_path / "test_api_chat.db")
    svc = TiffinService(test_db)
    svc.subscribe(name="Ramesh Kumar", phone="9876543210", plan_id="standard_veg", address="Mumbai", start_date=date(2026, 10, 1))
    
    web_module.service = svc
    web_module.chatbot = TiffinChatbot(svc)
    app.config["TESTING"] = True

    with app.test_client() as client:
        # 1. Test Assistant Page rendering
        r_page = client.get("/assistant")
        assert r_page.status_code == 200
        assert "Annapurna Intelligent Assistant" in r_page.data.decode("utf-8")
        assert "Transparent Reasoning Steps" in r_page.data.decode("utf-8")

        # 2. Test /api/chat with valid inquiry
        r_chat = client.post("/api/chat", json={"message": "What plans do you have?"})
        assert r_chat.status_code == 200
        data = r_chat.get_json()
        assert data["success"] is True
        assert "Standard Veg" in data["reply"]
        assert len(data["reasoning"]) > 0
        assert data["intent"] == "plans_inquiry"

        # 3. Test /api/chat with empty message
        r_empty = client.post("/api/chat", json={"message": ""})
        assert r_empty.status_code == 400

        # 4. Test /api/chat with phone context
        r_phone = client.post("/api/chat", json={"message": "check my account", "phone": "9876543210"})
        assert r_phone.status_code == 200
        data_phone = r_phone.get_json()
        assert data_phone["success"] is True
        assert "Ramesh Kumar" in data_phone["reply"]
