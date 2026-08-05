from typing import Annotated, Literal, Optional, Sequence, TypedDict
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agents import (
    create_intake_agent,
    create_general_support_agent,
    create_resolution_agent,
)
from models import AgentResponse, IntentEnum
from utils.logger import logger
from utils.observability import trace_node, pretty_format

# Instantiate agents
intake_agent = create_intake_agent()
general_support_agent = create_general_support_agent()
resolution_agent = create_resolution_agent()


class ConversationState(TypedDict):
    """LangGraph conversation state."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    intent: Optional[str]
    action: Optional[str]
    reason: Optional[str]
    final_response: Optional[AgentResponse]
    request_id: Optional[str]


@trace_node("Intake")
def intake_node(state: ConversationState) -> ConversationState:
    """Triage and classify the customer's query using the Intake Agent."""
    latest_msg = state["messages"][-1].content if state.get("messages") else ""
    
    logger.info("--------------------------------")
    logger.info("INTAKE AGENT")
    logger.info("--------------------------------")
    logger.info(f"Latest user message: {latest_msg}")
    
    result = intake_agent.invoke({"messages": state["messages"]})
    
    # Extract structured response from triage
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
        
        # If the Intake Agent can respond immediately, record the response and short-circuit
        if state["action"] == "respond":
            response_text = intake_val.response or ""
            state["final_response"] = AgentResponse(
                message=response_text,
                requires_escalation=False
            )
            state["messages"].append(AIMessage(content=response_text))
            logger.info(f"Triage: Instant response ready. Short-circuiting workflow. Reason: {state['reason']}")
        else:
            logger.info(f"Triage: Downstream workflow required. Proceeding to {state['intent']} node.")
    else:
        # Fallback triage decision
        state["intent"] = IntentEnum.GENERAL.value
        state["action"] = "respond"
        state["reason"] = "other"
        fallback_msg = "I'm sorry, I encountered an error."
        state["final_response"] = AgentResponse(message=fallback_msg, requires_escalation=False)
        state["messages"].append(AIMessage(content=fallback_msg))
        logger.warn("Triage: Failed to obtain structured IntakeOutput. Applying fallback response.")

    return state


@trace_node("General Support")
def general_support_node(state: ConversationState) -> ConversationState:
    """Process query using the General Support Agent."""
    result = general_support_agent.invoke({"messages": state["messages"]})
    
    response = result.get("structured_response")
    if response:
        state["final_response"] = response
        # Append the message to the conversation history
        state["messages"].append(AIMessage(content=response.message))
    else:
        # Fallback in case of formatting error
        fallback_msg = result["messages"][-1].content if result.get("messages") else "I'm sorry, I encountered an error."
        fallback_resp = AgentResponse(message=fallback_msg, requires_escalation=False)
        state["final_response"] = fallback_resp
        state["messages"].append(AIMessage(content=fallback_msg))

    return state


@trace_node("Resolution")
def resolution_node(state: ConversationState) -> ConversationState:
    """Process query using the Returns & Resolution Agent."""
    result = resolution_agent.invoke({"messages": state["messages"]})
    
    response = result.get("structured_response")
    if response:
        state["final_response"] = response
        state["messages"].append(AIMessage(content=response.message))
    else:
        # Fallback
        fallback_msg = result["messages"][-1].content if result.get("messages") else "I'm sorry, I encountered an error."
        fallback_resp = AgentResponse(message=fallback_msg, requires_escalation=False)
        state["final_response"] = fallback_resp
        state["messages"].append(AIMessage(content=fallback_msg))

    return state


def route(state: ConversationState) -> Literal["resolution", "general", "__end__"]:
    """Conditional edge router deciding whether to short-circuit or execute workflow."""
    if state.get("action") == "respond":
        return "__end__"
    if state.get("intent") == IntentEnum.RETURNS.value:
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
