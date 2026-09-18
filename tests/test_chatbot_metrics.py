from datetime import date
import pytest
from tiffin.chatbot import TiffinChatbot
from tiffin.service import TiffinService
from web.app import app
import web.app as web_module


@pytest.fixture
def test_svc(tmp_path):
    test_db = str(tmp_path / "test_metrics.db")
    service = TiffinService(test_db)
    # Seed customer
    service.subscribe(
        name="Sunita Rao",
        phone="9845012345",
        plan_id="south_veg_meals",
        address="102 Palm Grove, Koramangala, Bengaluru",
        notes="Extra moru",
        start_date=date(2026, 10, 1),
    )
    return service


@pytest.fixture
def chatbot(test_svc):
    return TiffinChatbot(test_svc)


def test_ai_metric_faithfulness_and_groundedness(chatbot):
    """
    Asserts Faithfulness and Groundedness metrics evaluate to 1.0 (100%)
    with zero hallucination across query intents.
    """
    res = chatbot.answer_query("What partner kitchens or restaurants do you have?")
    assert res["intent"] == "kitchens_inquiry"
    m = res["metrics"]
    assert m["faithfulness"] == 1.0
    assert m["groundedness"] == 1.0
    assert m["hallucination_detected"] is False
    assert m["verification_status"] == "VERIFIED_ZERO_HALLUCINATION"
    assert len(res["sources_cited"]) >= 5  # 5 partner kitchens cited
    assert "Shree Krishna" in res["reply"]
    assert "Dabbawala Express" in res["reply"]
    assert "Spice Route" in res["reply"]
    assert "Punjab Da Dhaba" in res["reply"]


def test_ai_metric_jain_satvik_specialty_grounding(chatbot):
    """
    Tests specific dietary query (Jain / Satvik food) matches
    Shree Krishna Gujarati & Jain Rasoi with accurate FSSAI and specialty.
    """
    res = chatbot.answer_query("Where can I get pure Jain and Satvik food without onion or garlic?")
    assert res["intent"] == "cuisine_inquiry"
    assert "Shree Krishna Gujarati & Jain Rasoi" in res["reply"]
    assert "FSSAI-12224026000889" in res["reply"]
    assert res["metrics"]["faithfulness"] == 1.0
    assert res["metrics"]["groundedness"] == 1.0
    assert res["metrics"]["hallucination_detected"] is False


def test_ai_metric_price_comparison(chatbot):
    """
    Tests comparing prices across all partner kitchens from lowest to highest.
    """
    res = chatbot.answer_query("Compare prices of all meal plans")
    assert res["intent"] == "price_comparison"
    assert "Price Comparison" in res["reply"]
    assert "Corporate Calorie-Smart Box" in res["reply"]
    assert res["metrics"]["faithfulness"] == 1.0
    assert res["metrics"]["groundedness"] == 1.0
    assert len(res["sources_cited"]) >= 10


def test_ai_metric_fssai_hygiene_safety(chatbot):
    """
    Tests FSSAI safety certifications lookup.
    """
    res = chatbot.answer_query("Are all your tiffin kitchens FSSAI certified?")
    assert res["intent"] == "fssai_hygiene"
    assert "FSSAI Food Safety" in res["reply"]
    assert "FSSAI-12223026000145" in res["reply"]
    assert res["metrics"]["faithfulness"] == 1.0
    assert res["metrics"]["groundedness"] == 1.0


def test_ai_metric_arithmetic_accuracy_on_simulation(chatbot):
    """
    Tests arithmetic accuracy metric on scenario pro-ration calculations.
    """
    # 22 weekdays in standard month. 5 days paused -> 17 delivered.
    # On Kathiyawadi Deluxe (Rs. 3600/mo):
    # Daily rate = 3600 / 22 = 163.636...
    # Delivered 17 days = 17 * 163.636... = 2781.82
    res = chatbot.answer_query("If I pause for 5 days on kathiyawadi deluxe, what will I pay?")
    assert res["intent"] == "simulation"
    assert "2,781.82" in res["reply"] or "2781.82" in res["reply"]
    m = res["metrics"]
    assert m["arithmetic_accuracy"] == 1.0
    assert m["faithfulness"] == 1.0
    assert m["groundedness"] == 1.0
    assert m["hallucination_detected"] is False


def test_ai_metric_customer_account_lookup(chatbot):
    """
    Tests customer phone lookup returns grounded dossier with 100% faithfulness.
    """
    res = chatbot.answer_query("Check my account bill for 9845012345")
    assert res["intent"] == "customer_lookup_success"
    assert "Sunita Rao" in res["reply"]
    assert "Spice Route South Indian Mess" in res["reply"] or "Dakshin" in res["reply"]
    m = res["metrics"]
    assert m["faithfulness"] == 1.0
    assert m["groundedness"] == 1.0
    assert m["arithmetic_accuracy"] == 1.0


def test_kitchens_web_view(test_svc):
    """
    Tests that /kitchens web view renders successfully with all 5 kitchens.
    """
    web_module.service = test_svc
    web_module.chatbot = TiffinChatbot(test_svc)
    app.config["TESTING"] = True

    with app.test_client() as client:
        r = client.get("/kitchens")
        assert r.status_code == 200
        html = r.data.decode("utf-8")
        assert "Partner Kitchens &amp; Tiffin Parlors" in html or "Partner Kitchens & Tiffin Parlors" in html
        assert "Annapurna Homestyle Kitchen" in html
        assert "Shree Krishna Gujarati &amp; Jain Rasoi" in html or "Shree Krishna Gujarati & Jain Rasoi" in html
        assert "Dabbawala Express Corporate Kitchen" in html
        assert "Spice Route South Indian Mess" in html
        assert "Punjab Da Dhaba Tiffin House" in html
        assert "FSSAI-12223026000145" in html


def test_api_chat_returns_sources_and_metrics(test_svc):
    """
    Tests that REST API endpoint /api/chat returns sources_cited and metrics object.
    """
    web_module.service = test_svc
    web_module.chatbot = TiffinChatbot(test_svc)
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.post("/api/chat", json={"message": "What are your meal plans and prices?"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "metrics" in data
        assert data["metrics"]["faithfulness"] == 1.0
        assert data["metrics"]["groundedness"] == 1.0
        assert data["metrics"]["hallucination_detected"] is False
        assert "sources_cited" in data
        assert len(data["sources_cited"]) > 0