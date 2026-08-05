from typing import Optional
from langchain_core.tools import tool
from models import (
    OrderLookupRequest,
    PolicyLookupRequest,
    EscalationRequest,
)
from services import OrdersService, PolicyService, EscalationService
from utils.observability import trace_tool

# Instantiate services
orders_service = OrdersService("data/orders.json")
policy_service = PolicyService("data/trendly_policy.md")
escalation_service = EscalationService()


@tool
@trace_tool("order_lookup")
def order_lookup(
    order_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    product_name: Optional[str] = None,
) -> str:
    """Search and retrieve order details from Trendly's order history.

    You must provide at least one of:
    - order_id: e.g. 'TR-4521'
    - customer_name: e.g. 'Ananya Rao'
    - product_name: e.g. 'Linen Wrap Dress'
    """
    req = OrderLookupRequest(
        order_id=order_id,
        customer_name=customer_name,
        product_name=product_name
    )
    res = orders_service.find_orders(req)
    return res.model_dump_json()


@tool
@trace_tool("policy_lookup")
def policy_lookup(
    query: str,
) -> str:
    """Search and retrieve sections from the Trendly Shipping & Returns Policy document.

    Use this to look up rules on return windows, hygiene product eligibility, final sale limits, 
    payout timelines, delayed orders store credits, and lost package policies.
    """
    req = PolicyLookupRequest(query=query)
    res = policy_service.find_policy(req)
    return res.model_dump_json()


@tool
@trace_tool("escalate")
def escalate(
    reason: str,
    summary: str,
) -> str:
    """Escalate the customer's request to a human support agent.

    Use this whenever a policy instructs you to escalate, when a refund needs to be handled
    manually (e.g. COD refund bank details), or when the user asks for a human.
    Provide a concise reason and a helpful summary of the issue.
    """
    req = EscalationRequest(reason=reason, summary=summary)
    res = escalation_service.create_ticket(req)
    return res.model_dump_json()
