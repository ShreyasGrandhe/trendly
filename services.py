import json
import re
from pathlib import Path
from uuid import uuid4
from models import (
    OrderLookupRequest,
    OrderLookupResponse,
    PolicyLookupRequest,
    PolicyLookupResponse,
    EscalationRequest,
    EscalationResponse,
)
from utils.logger import logger
from utils.observability import trace_service



class OrdersService:
    """Service to load and search order history."""

    def __init__(self, data_path: str):
        self.data_path = Path(data_path)
        with open(self.data_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    @trace_service("OrdersService")
    def find_orders(self, request: OrderLookupRequest) -> OrderLookupResponse:
        orders = self.data.get("orders", [])
        customers = self.data.get("customers", [])
        matched_orders = []

        # Extract search criteria
        order_id = request.order_id.strip() if request.order_id else None
        customer_name = request.customer_name.strip().lower() if request.customer_name else None
        product_name = request.product_name.strip().lower() if request.product_name else None

        if order_id:
            logger.info(f"[OrdersService] Searching by Order ID: {order_id}")
        if customer_name:
            logger.info(f"[OrdersService] Searching by Customer Name: {customer_name}")
        if product_name:
            logger.info(f"[OrdersService] Searching by Product: {product_name}")

        if not order_id and not customer_name and not product_name:
            return OrderLookupResponse(
                success=False,
                orders=[],
                message="Please provide at least one search parameter (order_id, customer_name, or product_name)."
            )

        # Map customer_id -> name for quick lookup
        cust_id_to_name = {c["customer_id"]: c["name"] for c in customers}

        for order in orders:
            is_match = True

            # Match order ID
            if order_id and order["order_id"].strip().lower() != order_id.lower():
                is_match = False

            # Match customer name
            if customer_name:
                c_name = cust_id_to_name.get(order["customer_id"], "").lower()
                if customer_name not in c_name:
                    is_match = False

            # Match product name in items
            if product_name:
                has_product = any(
                    product_name in item["name"].strip().lower()
                    for item in order.get("items", [])
                )
                if not has_product:
                    is_match = False

            if is_match:
                order_copy = dict(order)
                order_copy["customer_name"] = cust_id_to_name.get(order["customer_id"], "Unknown")
                matched_orders.append(order_copy)

        logger.info(f"[OrdersService] Number of matches found: {len(matched_orders)}")
        if matched_orders:
            logger.info(f"[OrdersService] Selected order: {matched_orders[0]['order_id']}")

        return OrderLookupResponse(
            success=True,
            orders=matched_orders,
            message=None if matched_orders else "No matching orders found."
        )


class PolicyService:
    """Service to parse and retrieve sections of the policy markdown."""

    def __init__(self, data_path: str):
        self.data_path = Path(data_path)
        with open(self.data_path, "r", encoding="utf-8") as f:
            self.content = f.read()
        self.sections = self._parse_sections()

    def _parse_sections(self):
        # Split markdown by sections (demarcated by '## ')
        parts = re.split(r'\n##\s+', self.content)
        sections = []

        # Intro text before the first '## '
        intro = parts[0].strip()
        if intro:
            sections.append(("Introduction / General Policies", intro))

        for part in parts[1:]:
            lines = part.strip().split('\n')
            header = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()
            sections.append((header, f"## {header}\n\n{body}"))

        return sections

    @trace_service("PolicyService")
    def find_policy(self, request: PolicyLookupRequest) -> PolicyLookupResponse:
        query = request.query.strip().lower()
        logger.info(f"[PolicyService] Query received: {request.query}")
        if not query:
            return PolicyLookupResponse(
                success=False,
                relevant_section="",
                message="Query cannot be empty."
            )

        # Scoring words (ignoring short stopwords/common words)
        search_terms = [w for w in re.split(r'\W+', query) if len(w) > 2]
        if not search_terms:
            search_terms = [query]

        # Generate bigrams for contiguous phrase matching
        bigrams = []
        if len(search_terms) > 1:
            bigrams = [" ".join(search_terms[i:i+2]) for i in range(len(search_terms) - 1)]

        best_section = None
        best_score = -1

        for header, content in self.sections:
            score = 0
            header_lower = header.lower()
            content_lower = content.lower()

            # 1. Contiguous phrase match boost
            for bigram in bigrams:
                if bigram in content_lower:
                    score += 25
                if bigram in header_lower:
                    score += 40

            # 2. Individual term search scoring
            for term in search_terms:
                if term in header_lower:
                    score += 5
                score += content_lower.count(term)

            if score > best_score:
                best_score = score
                best_section = content

        if best_score > 0 and best_section:
            # Extract header from the matched section
            lines = best_section.split("\n")
            section_name = lines[0].replace("##", "").strip() if lines else "Unknown"
            logger.info(f"[PolicyService] Section matched: {section_name}")
            logger.info(f"[PolicyService] Clause matched: {section_name}")
            return PolicyLookupResponse(
                success=True,
                relevant_section=best_section
            )

        # Fallback to general/intro text if no match
        fallback = self.sections[0][1] if self.sections else self.content
        logger.info(f"[PolicyService] No specific match found. Falling back to introduction.")
        return PolicyLookupResponse(
            success=True,
            relevant_section=fallback,
            message="No specific section matched the search perfectly. Returning general policy text."
        )


class EscalationService:
    """Service to create mock escalation support tickets."""

    @trace_service("EscalationService")
    def create_ticket(self, request: EscalationRequest) -> EscalationResponse:
        ticket_id = f"ESC-{uuid4().hex[:8].upper()}"
        logger.info(f"[EscalationService] Ticket generated: {ticket_id} | Reason: {request.reason}")
        return EscalationResponse(
            success=True,
            ticket_id=ticket_id,
            reason=request.reason,
            message=(
                f"Your request has been escalated to a human support agent. "
                f"Your ticket ID is {ticket_id}."
            )
        )
