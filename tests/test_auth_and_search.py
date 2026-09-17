import pytest
from tiffin.service import TiffinService


@pytest.fixture
def service(tmp_path):
    db_file = str(tmp_path / "test_auth.db")
    return TiffinService(db_file)


def test_default_admin_exists(service):
    admin = service.authenticate_user("admin", "admin123")
    assert admin is not None
    assert admin.username == "admin"
    assert admin.role == "owner"


def test_user_registration_and_authentication(service):
    user = service.register_user(
        username="jaipur_kitchen",
        password="securepassword",
        email="kitchen@jaipur.com",
    )
    assert user.id is not None
    assert user.username == "jaipur_kitchen"

    # Authenticate successfully
    auth = service.authenticate_user("jaipur_kitchen", "securepassword")
    assert auth is not None
    assert auth.email == "kitchen@jaipur.com"

    # Reject wrong password
    bad_auth = service.authenticate_user("jaipur_kitchen", "wrongpassword")
    assert bad_auth is None

    # Reject duplicate username
    with pytest.raises(ValueError, match="already exists"):
        service.register_user("jaipur_kitchen", "anotherpassword")


def test_customer_search_and_pagination(service):
    # Add 12 customers
    for i in range(1, 13):
        service.subscribe(
            name=f"Customer {i:02d}",
            phone=f"98000000{i:02d}",
            plan_id="standard_veg",
            address=f"Flat {i}, Lotus Towers",
        )

    # Search by partial name "Customer 0"
    results, total, pages = service.search_customers(query="Customer 0", page=1, per_page=5)
    assert total == 9  # Customer 01 to 09
    assert pages == 2
    assert len(results) == 5

    # Page 2
    p2_results, _, _ = service.search_customers(query="Customer 0", page=2, per_page=5)
    assert len(p2_results) == 4

    # Search by address
    addr_results, total_addr, _ = service.search_customers(query="Lotus Towers")
    assert total_addr == 12

    # Sorting
    desc_results, _, _ = service.search_customers(query="", sort_by="name", order="desc", page=1, per_page=12)
    assert desc_results[0].name == "Customer 12"
    assert desc_results[-1].name == "Customer 01"
