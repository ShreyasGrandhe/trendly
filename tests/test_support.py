import pytest
from services import OrdersService, PolicyService, EscalationService
from models import (
    OrderLookupRequest,
    PolicyLookupRequest,
    EscalationRequest,
)

# Initialize services with test file paths
orders_service = OrdersService("data/orders.json")
policy_service = PolicyService("data/trendly_policy.md")
escalation_service = EscalationService()


def test_order_lookup_by_id():
    # Test valid order ID
    req = OrderLookupRequest(order_id="TR-4521")
    res = orders_service.find_orders(req)
    assert res.success is True
    assert len(res.orders) == 1
    assert res.orders[0]["order_id"] == "TR-4521"
    assert res.orders[0]["customer_name"] == "Ananya Rao"


def test_order_lookup_by_customer():
    # Test customer name substring match
    req = OrderLookupRequest(customer_name="Marcus")
    res = orders_service.find_orders(req)
    assert res.success is True
    assert len(res.orders) == 3  # TR-4522, TR-4526, TR-4530
    assert any(o["order_id"] == "TR-4530" for o in res.orders)


def test_order_lookup_by_product():
    # Test product name search match
    req = OrderLookupRequest(product_name="Bomber Jacket")
    res = orders_service.find_orders(req)
    assert res.success is True
    assert len(res.orders) == 1
    assert res.orders[0]["order_id"] == "TR-4523"


def test_order_lookup_no_criteria():
    req = OrderLookupRequest()
    res = orders_service.find_orders(req)
    assert res.success is False
    assert len(res.orders) == 0


def test_policy_lookup_shipping():
    # Search for shipping charges
    req = PolicyLookupRequest(query="shipping charges fee cost")
    res = policy_service.find_policy(req)
    assert res.success is True
    assert "Shipping charges" in res.relevant_section
    assert "₹1,499" in res.relevant_section


def test_policy_lookup_hygiene_non_returnable():
    # Search for jewellery returns
    req = PolicyLookupRequest(query="jewellery non-returnable return earrings")
    res = policy_service.find_policy(req)
    assert res.success is True
    assert "Non-returnable categories" in res.relevant_section
    assert "Jewellery" in res.relevant_section


def test_policy_lookup_final_sale():
    req = PolicyLookupRequest(query="final sale size exchange refund")
    res = policy_service.find_policy(req)
    assert res.success is True
    assert "Final sale items" in res.relevant_section


def test_escalation():
    req = EscalationRequest(
        reason="Lost parcel claim",
        summary="Customer Marcus Bell reports order TR-4526 is marked lost by carrier."
    )
    res = escalation_service.create_ticket(req)
    assert res.success is True
    assert res.ticket_id.startswith("ESC-")
    assert "escalated" in res.message
