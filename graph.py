import os
import re
import json
from typing import Annotated, Literal, Optional, Sequence, TypedDict
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model

from agents import create_intake_agent
from models import AgentResponse, IntentEnum
from utils.logger import logger
from utils.observability import trace_node, pretty_format, LangChainObservabilityHandler
from tools import order_lookup, policy_lookup, escalate, orders_service
from prompts import GENERAL_SUPPORT_SYSTEM_PROMPT, RESOLUTION_SYSTEM_PROMPT

# Instantiate triage agent
intake_agent = create_intake_agent()

# Load env configurations for direct LLM calls
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai")


def extract_order_id(text: str) -> Optional[str]:
    """Extract and normalize Order ID from text, e.g. TR-4525 or 4525 -> TR-4525."""
    match = re.search(r'\b(TR-)?\d{4,}\b', text, re.IGNORECASE)
    if match:
        val = match.group(0).upper()
        if not val.startswith("TR-"):
            val = f"TR-{val}"
        return val
    return None


class ConversationState(TypedDict):
    """LangGraph conversation state."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    intent: Optional[str]
    action: Optional[str]
    reason: Optional[str]
    
    # State-driven persistent fields
    workflow: Optional[str]
    requires_order: Optional[bool]
    requires_policy: Optional[bool]
    missing_entity: Optional[str]
    entities: Optional[dict]
    workflow_status: Optional[str]
    
    final_response: Optional[AgentResponse]
    request_id: Optional[str]


def summarize_order_json(raw_json: str) -> str:
    """Helper to convert raw order JSON into a compact reasoning summary."""
    try:
        data = json.loads(raw_json)
        orders = data.get("orders", [])
        if not orders:
            return "No orders found."
        
        order = orders[0]
        items_summary = []
        for item in order.get("items", []):
            items_summary.append(
                f"- Name: {item.get('name')}, Category: {item.get('category')}, "
                f"Size: {item.get('size')}, Qty: {item.get('qty')}, "
                f"Price: {item.get('price')}, Final Sale: {item.get('final_sale')}"
            )
            
        return (
            f"Order ID: {order.get('order_id')}\n"
            f"Status: {order.get('status')}\n"
            f"Placed At: {order.get('placed_at')}\n"
            f"Expected Delivery: {order.get('expected_delivery')}\n"
            f"Carrier: {order.get('carrier')}\n"
            f"Tracking Number: {order.get('tracking_number')}\n"
            f"Delivered At: {order.get('delivered_at')}\n"
            f"Payment Method: {order.get('payment_method')}\n"
            f"Shipping City: {order.get('shipping_city')}\n"
            f"Items:\n" + "\n".join(items_summary)
        )
    except Exception as e:
        logger.error(f"Error parsing order data for summary: {e}")
        return raw_json


def parse_policy_json(raw_json: str) -> str:
    """Helper to extract the text section content from PolicyLookupResponse JSON."""
    try:
        data = json.loads(raw_json)
        return data.get("relevant_section", "No policy matches found.")
    except Exception:
        return raw_json

def verify_customer_authorization(state: ConversationState) -> bool:
    """Enforce security policy: prevent discussing orders belonging to a different customer,
    and validate that the order exists (re-prompting or escalating if not found)."""
    order_id = state["entities"].get("order_id")
    if not order_id:
        return True

    from models import OrderLookupRequest
    try:
        res = orders_service.find_orders(OrderLookupRequest(order_id=order_id))
        if res.success:
            if not res.orders:
                # ORDER NOT FOUND!
                not_found_count = state["entities"].get("not_found_count", 0) + 1
                state["entities"]["not_found_count"] = not_found_count
                
                ticket_id = None
                requires_escalation = False
                
                if not_found_count >= 2:
                    # 2nd time: escalate!
                    requires_escalation = True
                    reason_text = f"Order ID {order_id} not found in Trendly order history after multiple attempts."
                    esc_raw = escalate.invoke({
                        "reason": reason_text,
                        "summary": f"User attempted to locate order {order_id} but it does not exist in the database. Failed {not_found_count} times."
                    })
                    try:
                        esc_data = json.loads(esc_raw)
                        ticket_id = esc_data.get("ticket_id")
                    except Exception as e:
                        logger.error(f"Error parsing order not found escalation: {e}")
                        
                    response_text = f"I'm sorry, but I still cannot find order {order_id} in our system. I have escalated this issue to our human support team to help you locate your order details. Your escalation ticket ID is {ticket_id or 'ESC-SUPPORT'}."
                else:
                    # 1st time: ask to check and try again
                    response_text = f"I'm sorry, but I couldn't find order {order_id} in our system. Could you please double-check the order number and let me know the correct one?"
                    
                state["action"] = "respond"
                state["workflow_status"] = "waiting_for_user" if not requires_escalation else "completed"
                state["missing_entity"] = "order_id" if not requires_escalation else None
                
                # Clear incorrect order_id so slot-filling can trigger next turn if not escalated
                if not requires_escalation and "order_id" in state["entities"]:
                    del state["entities"]["order_id"]
                    
                state["final_response"] = AgentResponse(
                    message=response_text,
                    requires_escalation=requires_escalation,
                    ticket_id=ticket_id
                )
                state["messages"].append(AIMessage(content=response_text))
                logger.warn(f"Authorization: Order ID {order_id} not found ({not_found_count} times).")
                return False
                
            # If order exists, perform customer ID mismatch verification
            current_customer_id = res.orders[0].get("customer_id")
            if current_customer_id:
                cached_customer_id = state["entities"].get("customer_id")
                if not cached_customer_id:
                    # First order ID checked, cache the customer_id for this session
                    state["entities"]["customer_id"] = current_customer_id
                    logger.info(f"Authorization: Cached customer_id '{current_customer_id}' for session.")
                elif cached_customer_id != current_customer_id:
                    # Increment decline count
                    decline_count = state["entities"].get("decline_count", 0) + 1
                    state["entities"]["decline_count"] = decline_count
                    
                    ticket_id = None
                    requires_escalation = False
                    
                    if decline_count >= 3:
                        requires_escalation = True
                        esc_raw = escalate.invoke({
                            "reason": f"Authorization verification discrepancies: user blocked {decline_count} times trying to access order {order_id} belonging to customer {current_customer_id}.",
                            "summary": f"User attempted to query order {order_id} belonging to customer {current_customer_id}, which does not match session customer {cached_customer_id}. User was blocked {decline_count} times."
                        })
                        try:
                            esc_data = json.loads(esc_raw)
                            ticket_id = esc_data.get("ticket_id")
                        except Exception as e:
                            logger.error(f"Error parsing authorization escalation ticket: {e}")
                            
                        decline_msg = f"I understand this is frustrating, and I sincerely apologize for the inconvenience. Since we have encountered multiple authorization discrepancies for order {order_id}, I have escalated this issue to our human support team to assist you further. Your support ticket ID is {ticket_id or 'ESC-SUPPORT'}."
                    elif decline_count == 2:
                        decline_msg = f"I apologize for the restriction, but our security policy prevents me from sharing details about order {order_id} because the account associated with it does not match this session. If you believe this is an error, please let me know, or I can connect you with our support team."
                    else:
                        decline_msg = f"I'm sorry, but I cannot discuss or provide information about order {order_id} as it belongs to a different customer account."
                        
                    state["action"] = "respond"
                    state["intent"] = "general"
                    state["reason"] = "other"
                    state["workflow_status"] = "completed"
                    state["final_response"] = AgentResponse(
                        message=decline_msg,
                        requires_escalation=requires_escalation,
                        ticket_id=ticket_id
                    )
                    state["messages"].append(AIMessage(content=decline_msg))
                    logger.warn(f"Authorization: Blocked cross-customer access ({decline_count} times). Attempted: {order_id} (Customer: {current_customer_id}) vs Session Customer: {cached_customer_id}")
                    return False
    except Exception as e:
        logger.error(f"Error validating customer authorization: {e}")
    return True


@trace_node("Intake")
def intake_node(state: ConversationState) -> ConversationState:
    """Triage the customer's query or slot-fill missing entities to continue the workflow."""
    latest_msg = state["messages"][-1].content if state.get("messages") else ""
    
    logger.info("--------------------------------")
    logger.info("INTAKE AGENT")
    logger.info("--------------------------------")
    logger.info(f"Latest user message: {latest_msg}")
    
    # Initialize entities dictionary if missing
    if "entities" not in state or state["entities"] is None:
        state["entities"] = {}
        
    # Check if workflow is currently waiting for a missing entity (e.g. order_id)
    if state.get("workflow_status") == "waiting_for_user":
        missing = state.get("missing_entity")
        if missing == "order_id":
            order_id = extract_order_id(latest_msg)
            if order_id:
                state["entities"]["order_id"] = order_id
                state["workflow_status"] = "ready"
                state["action"] = "execute_workflow"
                state["missing_entity"] = None
                logger.info(f"Triage: Slot-filled missing entity 'order_id' with value '{order_id}'. Status updated to ready.")
                if not verify_customer_authorization(state):
                    return state
                return state
            else:
                logger.info("Triage: Waiting for Order ID but none matched in latest query. Re-triaging intent.")

    # Execute Intake LLM call for fresh queries or fallback re-classification
    result = intake_agent.invoke({"messages": state["messages"]})
    
    intake_val = result.get("structured_response")
    if intake_val:
        logger.info(f"Structured intake output:\n{pretty_format(intake_val)}")
        state["intent"] = (
            intake_val.intent.value 
            if hasattr(intake_val.intent, "value") 
            else intake_val.intent
        )
        state["action"] = (
            intake_val.action.value 
            if hasattr(intake_val.action, "value") 
            else intake_val.action
        )
        state["reason"] = (
            intake_val.reason.value 
            if hasattr(intake_val.reason, "value") 
            else intake_val.reason
        )
        
        # Populate persistent workflow details
        state["workflow"] = (
            intake_val.workflow.value 
            if hasattr(intake_val.workflow, "value") 
            else intake_val.workflow
        )
        state["requires_order"] = intake_val.requires_order
        state["requires_policy"] = intake_val.requires_policy
        state["missing_entity"] = (
            intake_val.missing_entity.value 
            if hasattr(intake_val.missing_entity, "value") 
            else intake_val.missing_entity
        )
        state["workflow_status"] = (
            intake_val.workflow_status.value 
            if hasattr(intake_val.workflow_status, "value") 
            else intake_val.workflow_status
        )
        
        # 1. Always check if a new Order ID is provided in the user's latest query, and override if found
        latest_order_id = extract_order_id(latest_msg)
        if latest_order_id:
            state["entities"]["order_id"] = latest_order_id
            logger.info(f"Triage: Set order_id to '{latest_order_id}' from latest message (overriding any old order_id).")
        
        # 2. If no order_id is in entities, scan the conversation history to recover it
        if not state["entities"].get("order_id"):
            for m in reversed(state["messages"][:-1]):  # scan history excluding latest message
                order_id = extract_order_id(m.content)
                if order_id:
                    state["entities"]["order_id"] = order_id
                    logger.info(f"Triage: Recovered order_id '{order_id}' from message history.")
                    break

        # Ensure consistent state flags if we now have order_id
        if state["entities"].get("order_id"):
            if state.get("missing_entity") == "order_id":
                state["missing_entity"] = None
            if state.get("workflow_status") == "waiting_for_user":
                state["workflow_status"] = "ready"
                state["action"] = "execute_workflow"
        
        # Run authorization check
        if not verify_customer_authorization(state):
            return state
        
        # If the Intake Agent can respond immediately, record response and short-circuit
        if state["action"] == "respond":
            response_text = intake_val.response or ""
            state["final_response"] = AgentResponse(
                message=response_text,
                requires_escalation=False
            )
            state["messages"].append(AIMessage(content=response_text))
            logger.info(f"Triage: Instant response ready. Short-circuiting workflow. Reason: {state['reason']}")
        else:
            logger.info(f"Triage: Downstream workflow ready. Proceeding to {state['intent']} node.")
    else:
        # Fallback triage decision
        state["intent"] = IntentEnum.GENERAL.value
        state["action"] = "respond"
        state["reason"] = "other"
        state["workflow_status"] = "completed"
        fallback_msg = "I'm sorry, I encountered an error."
        state["final_response"] = AgentResponse(message=fallback_msg, requires_escalation=False)
        state["messages"].append(AIMessage(content=fallback_msg))
        logger.warn("Triage: Failed to obtain structured IntakeOutput. Applying fallback response.")

    return state


@trace_node("General Support")
def general_support_node(state: ConversationState) -> ConversationState:
    """Process query using deterministic tool pre-fetching based on state and a single LLM call."""
    latest_query = state["messages"][-1].content if state.get("messages") else ""
    entities = state.get("entities") or {}
    order_id = entities.get("order_id")

    context_parts = []
    
    # 1. Trigger Policy Lookup if requires_policy is true in persistent state
    if state.get("requires_policy"):
        policy_query = latest_query
        if state.get("workflow"):
            policy_query = f"policy for {state.get('workflow')}"
        policy_res = policy_lookup.invoke({"query": policy_query})
        policy_section = parse_policy_json(policy_res)
        context_parts.append(f"=== RELEVANT STORE POLICY ===\n{policy_section}")

    # 2. Trigger Order Lookup if requires_order is true in persistent state and order ID is available
    if state.get("requires_order") and order_id:
        order_res = order_lookup.invoke({"order_id": order_id})
        order_summary = summarize_order_json(order_res)
        context_parts.append(f"=== ORDER HISTORY DETAILS ===\n{order_summary}")

    # Crop history to the current user query + minimal context (latest 3 messages)
    truncated_history = list(state["messages"][-3:]) if len(state["messages"]) >= 3 else list(state["messages"])

    # Initialize non-agent single-invocation model
    model = init_chat_model(
        MODEL_NAME,
        model_provider=MODEL_PROVIDER,
        temperature=0,
        callbacks=[LangChainObservabilityHandler("General Support Agent")]
    )
    structured_model = model.with_structured_output(AgentResponse)

    # Compile the prompt with context injected into system instructions
    context_str = "\n\n".join(context_parts)
    system_prompt = f"{GENERAL_SUPPORT_SYSTEM_PROMPT}\n\n{context_str}"
    
    messages = [SystemMessage(content=system_prompt)] + truncated_history
    
    # Call the model directly
    logger.info("General Node: Triggering single LLM call for response synthesis.")
    response = structured_model.invoke(messages)
    
    state["final_response"] = response
    state["messages"].append(AIMessage(content=response.message))
    
    # Complete workflow status
    state["workflow_status"] = "completed"
    
    return state


@trace_node("Resolution")
def resolution_node(state: ConversationState) -> ConversationState:
    """Orchestrate compact context pre-fetching and invoke the single-turn Resolution LLM based on state."""
    latest_query = state["messages"][-1].content if state.get("messages") else ""
    entities = state.get("entities") or {}
    order_id = entities.get("order_id")

    context_parts = []
    
    # 1. Trigger Order Lookup if requires_order is true in persistent state and order ID is available
    if state.get("requires_order") and order_id:
        order_res = order_lookup.invoke({"order_id": order_id})
        order_summary = summarize_order_json(order_res)
        context_parts.append(f"=== RELEVANT ORDER DETAILS ===\n{order_summary}")
        
    # 2. Trigger Policy Lookup if requires_policy is true in persistent state
    if state.get("requires_policy"):
        policy_query = latest_query
        if state.get("workflow"):
            policy_query = f"policy for {state.get('workflow')}"
        policy_res = policy_lookup.invoke({"query": policy_query})
        policy_section = parse_policy_json(policy_res)
        context_parts.append(f"=== RELEVANT POLICY SECTIONS ===\n{policy_section}")

    # Crop history to the current user query + minimal context (latest 3 messages)
    truncated_history = list(state["messages"][-3:]) if len(state["messages"]) >= 3 else list(state["messages"])

    # Initialize single-invocation model for policy reasoning
    model = init_chat_model(
        MODEL_NAME,
        model_provider=MODEL_PROVIDER,
        temperature=0,
        callbacks=[LangChainObservabilityHandler("Resolution Agent")]
    )
    structured_model = model.with_structured_output(AgentResponse)

    # Compile system instructions with pre-fetched compact context
    context_str = "\n\n".join(context_parts)
    system_prompt = f"{RESOLUTION_SYSTEM_PROMPT}\n\n=== COMPACT REASONING CONTEXT ===\n{context_str}"
    
    messages = [SystemMessage(content=system_prompt)] + truncated_history
    
    logger.info("Resolution Node: Triggering single LLM call for policy reasoning.")
    response = structured_model.invoke(messages)
    
    # Deterministic escalation execution if the model requests handoff
    if response.requires_escalation:
        logger.info("Resolution Node: Escalation requested. Deterministically running Escalation Tool.")
        esc_raw = escalate.invoke({
            "reason": f"Resolution Agent reasoning handoff: {response.message}",
            "summary": f"User Query: {latest_query}\nOrder ID: {order_id}\nResolution Text: {response.message}"
        })
        try:
            esc_data = json.loads(esc_raw)
            response.ticket_id = esc_data.get("ticket_id")
            # Append ticket notification to final message
            response.message = f"{response.message} Your escalation ticket ID is {response.ticket_id}."
        except Exception as e:
            logger.error(f"Error parsing escalation response: {e}")
            
    state["final_response"] = response
    state["messages"].append(AIMessage(content=response.message))

    # Complete workflow status
    state["workflow_status"] = "completed"

    return state


def route(state: ConversationState) -> Literal["resolution", "general", "__end__"]:
    """Conditional edge router deciding whether to short-circuit or execute workflow based on state."""
    if state.get("action") == "respond":
        return "__end__"
    if state.get("workflow_status") == "waiting_for_user":
        return "__end__"
    if state.get("intent") in ["returns", "resolution"]:
        return "resolution"
    return "general"


# Build the Graph Workflow
builder = StateGraph(ConversationState)

builder.add_node("intake", intake_node)
builder.add_node("general", general_support_node)
builder.add_node("resolution", resolution_node)

builder.add_edge(START, "intake")
builder.add_conditional_edges(
    "intake",
    route,
    {
        "resolution": "resolution",
        "general": "general",
        "__end__": END,
    },
)
builder.add_edge("general", END)
builder.add_edge("resolution", END)

graph = builder.compile()

#graph