import time
import traceback
from uuid import uuid4
import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Load environment variables (API Key)
load_dotenv()

from graph import graph
from models import AgentResponse
from utils.logger import logger
from utils.observability import set_request_context, pretty_format

st.set_page_config(
    page_title="Trendly Support Assistant",
    page_icon="🛍️",
    layout="centered"
)

st.title("Trendly Agentic Support Assistant 🛍️")
st.write("Interact with the Trendly support workflow in real-time. The sidebar tracks session state and classification details.")

# Sidebar controls
st.sidebar.title("Session Controls")
session_id = st.sidebar.text_input("Session ID", value="default-session")

# Initialize global session storage in Streamlit state
if "sessions" not in st.session_state:
    st.session_state["sessions"] = {}

if session_id not in st.session_state["sessions"]:
    st.session_state["sessions"][session_id] = {
        "messages": [],
        "intent": None,
        "action": None,
        "reason": None,
        
        # State-driven persistent fields
        "workflow": None,
        "requires_order": None,
        "requires_policy": None,
        "missing_entity": None,
        "entities": {},
        "workflow_status": None,
        
        "final_response": None,
    }

session_state = st.session_state["sessions"][session_id]

# Sidebar Status Display
st.sidebar.divider()
st.sidebar.subheader("Active Session State")
st.sidebar.write(f"**Intent Classifier:** `{session_state['intent'] or 'Unclassified'}`")
st.sidebar.write(f"**Triage Action:** `{session_state['action'] or 'None'}`")
st.sidebar.write(f"**Triage Reason:** `{session_state['reason'] or 'None'}`")
st.sidebar.write(f"**Workflow Status:** `{session_state['workflow_status'] or 'None'}`")
st.sidebar.write(f"**Missing Entity:** `{session_state['missing_entity'] or 'None'}`")
st.sidebar.write(f"**Entities:** `{session_state['entities']}`")

if session_state.get("final_response"):
    resp: AgentResponse = session_state["final_response"]
    st.sidebar.write(f"**Escalation Status:** `{'Escalated' if resp.requires_escalation else 'Resolved'}`")
    if resp.ticket_id:
        st.sidebar.write(f"**Ticket ID:** `{resp.ticket_id}`")

if st.sidebar.button("Reset Session / Clear History"):
    st.session_state["sessions"][session_id] = {
        "messages": [],
        "intent": None,
        "action": None,
        "reason": None,
        
        "workflow": None,
        "requires_order": None,
        "requires_policy": None,
        "missing_entity": None,
        "entities": {},
        "workflow_status": None,
        
        "final_response": None,
    }
    st.rerun()

# Display conversational history
for msg in session_state["messages"]:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.write(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.write(msg.content)

# User Chat Input
if prompt := st.chat_input("Enter your request here (e.g. 'I want to track order TR-4521')..."):
    # Display user message
    with st.chat_message("user"):
        st.write(prompt)
    session_state["messages"].append(HumanMessage(content=prompt))

    # Generate unique Request ID
    request_id = str(uuid4())
    session_state["request_id"] = request_id
    
    # Initialize request context trace
    trace = set_request_context(request_id)
    
    logger.info(f"UI: Chat prompt submitted: '{prompt}' for session '{session_id}'")

    # Invoke the LangGraph workflow
    with st.spinner("Processing request..."):
        try:
            # Run graph with Request ID metadata & tags
            result = graph.invoke(
                session_state,
                config={
                    "metadata": {"request_id": request_id},
                    "tags": [request_id]
                }
            )
            
            # Persist updated history & intent in state
            session_state["messages"] = result["messages"]
            session_state["intent"] = result.get("intent")
            session_state["action"] = result.get("action")
            session_state["reason"] = result.get("reason")
            
            # Persist workflow state-driven properties
            session_state["workflow"] = result.get("workflow")
            session_state["requires_order"] = result.get("requires_order")
            session_state["requires_policy"] = result.get("requires_policy")
            session_state["missing_entity"] = result.get("missing_entity")
            session_state["entities"] = result.get("entities")
            session_state["workflow_status"] = result.get("workflow_status")
            
            # Retrieve final structured response
            final_response: AgentResponse = result.get("final_response")
            
            latency_ms = (time.time() - trace.start_time) * 1000
            
            if final_response:
                session_state["final_response"] = final_response
                response_text = final_response.message
                requires_escalation = final_response.requires_escalation
                ticket_id = final_response.ticket_id
            else:
                fallback_msg = result["messages"][-1].content if result.get("messages") else "I'm sorry, I encountered an error."
                response_text = fallback_msg
                requires_escalation = False
                ticket_id = None

            with st.chat_message("assistant"):
                st.write(response_text)
                if requires_escalation and ticket_id:
                    st.error(f"⚠️ Handoff Triggered! Ticket ID: **{ticket_id}**")
                    
            # Print Final Execution Summary to the console
            logger.info("======================================")
            logger.info("FINAL EXECUTION SUMMARY")
            logger.info("======================================")
            logger.info(f"Request ID: {request_id}")
            logger.info(f"Intent: {result.get('intent')}")
            logger.info(f"Triage Action: {result.get('action')}")
            logger.info(f"Triage Reason: {result.get('reason')}")
            logger.info(f"Workflow Status: {result.get('workflow_status')}")
            logger.info(f"Missing Entity: {result.get('missing_entity')}")
            logger.info(f"Entities: {result.get('entities')}")
            logger.info(f"Nodes Executed: {', '.join(trace.nodes_executed)}")
            logger.info(f"Tools Executed: {', '.join(trace.tools_executed)}")
            logger.info(f"Execution Order: {' -> '.join(trace.nodes_executed)}")
            logger.info(f"Router Decision: {trace.router_decision}")
            
            logger.info("Tool Results:")
            for tr in trace.tool_results:
                logger.info(f"  - {tr['tool']} ({tr['duration_ms']:.2f}ms)")
                
            logger.info(f"Final Structured Output:\n{pretty_format(final_response or trace.final_structured_output)}")
            logger.info(f"Final Response: {response_text}")
            logger.info(f"Total Latency: {latency_ms:.2f}ms")
            logger.info("======================================")
            
            # Rerun to update the sidebar values
            st.rerun()
            
        except Exception as e:
            logger.error(f"!!! EXCEPTION OCCURRED DURING UIs CHAT LIFE CYCLE !!!")
            logger.error(f"Request ID: {request_id}")
            logger.error(f"Exception: {e}")
            logger.error(traceback.format_exc())
            st.error(f"Error running assistant workflow: {e}")
