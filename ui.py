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

# Custom Premium CSS Injection - Forcing Light/White Theme everywhere
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');

/* Force Light Theme Colors across entire outer viewports, headers, and bottom sticky wrappers */
html, body, 
[data-testid="stAppViewContainer"], 
[data-testid="stHeader"], 
[data-testid="stBottom"],
.stBottom,
.stApp {
    background-color: #ffffff !important;
    color: #0f172a !important;
}

/* Main font override */
html, body, [class*="st-key"] {
    font-family: 'Inter', sans-serif !important;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Outfit', sans-serif !important;
    color: #0f172a !important;
}

/* Sidebar light branding */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
    background-color: #f8fafc !important;
    border-right: 1px solid #e2e8f0 !important;
}

/* Sidebar elements text color fix */
[data-testid="stSidebar"] p, 
[data-testid="stSidebar"] span, 
[data-testid="stSidebar"] h1, 
[data-testid="stSidebar"] h2, 
[data-testid="stSidebar"] h3 {
    color: #0f172a !important;
}

/* Sidebar input elements white background override */
[data-testid="stSidebar"] input, 
[data-testid="stSidebar"] div[data-baseweb="input"] {
    background-color: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
}

/* Button style override (Reset session etc) to be clean white and slate text */
.stButton button {
    background-color: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05) !important;
}
.stButton button:hover {
    background-color: #f1f5f9 !important;
    color: #0f172a !important;
    border-color: #94a3b8 !important;
}

/* Custom styled page header */
.header-container {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 50%, #3730a3 100%);
    padding: 30px;
    border-radius: 16px;
    color: white !important;
    margin-bottom: 28px;
    box-shadow: 0 10px 15px -3px rgba(99, 102, 241, 0.15), 0 4px 6px -4px rgba(99, 102, 241, 0.15);
}
.header-title {
    font-size: 32px;
    font-weight: 700;
    margin: 0;
    color: white !important;
    letter-spacing: -0.02em;
}
.header-subtitle {
    font-size: 14px;
    opacity: 0.9;
    margin-top: 8px;
    margin-bottom: 0;
    line-height: 1.5;
    color: rgba(255, 255, 255, 0.9) !important;
}

/* Chat bubble styling overrides to look clean in light theme */
[data-testid="stChatMessage"] {
    background-color: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    margin-bottom: 12px !important;
}
[data-testid="stChatMessage"] p, 
[data-testid="stChatMessage"] span, 
[data-testid="stChatMessage"] div {
    color: #0f172a !important;
}

/* Chat input outer bar background color override to white */
[data-testid="stChatInput"], [data-testid="stBottom"] > div {
    background-color: #ffffff !important;
}
/* Chat input wrapper layout styling */
[data-testid="stChatInput"] > div {
    position: relative !important;
    background-color: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
}
/* Chat input textarea override */
[data-testid="stChatInput"] textarea, div[data-baseweb="textarea"] {
    background-color: #ffffff !important;
    color: #0f172a !important;
}

/* Style input placeholders to be visible slate gray */
[data-testid="stChatInput"] textarea::placeholder {
    color: #64748b !important;
    opacity: 1.0 !important;
}
[data-testid="stChatInput"] textarea::-webkit-input-placeholder {
    color: #64748b !important;
    opacity: 1.0 !important;
}

/* Always-blinking mock cursor right after placeholder text when empty and unfocused */
[data-testid="stChatInput"] textarea:placeholder-shown:not(:focus) ~ button::before {
    content: "|" !important;
    position: absolute !important;
    left: 220px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    color: #4f46e5 !important;
    font-weight: 400 !important;
    font-size: 18px !important;
    animation: cursor-blink 1s step-end infinite !important;
    pointer-events: none !important;
}

@keyframes cursor-blink {
    from, to { opacity: 0; }
    50% { opacity: 1; }
}

/* Style send button to be highly visible with indigo background and white arrow */
[data-testid="stChatInput"] button {
    background-color: #4f46e5 !important;
    color: #ffffff !important;
    opacity: 1.0 !important;
}
[data-testid="stChatInput"] button:hover {
    background-color: #4338ca !important;
}
[data-testid="stChatInput"] button svg {
    fill: #ffffff !important;
    stroke: #ffffff !important;
}

/* State cards */
.state-card {
    background-color: white !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    margin-bottom: 16px;
}
.state-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid #f1f5f9;
}
.state-row:last-child {
    border-bottom: none;
}
.state-label {
    font-size: 13px;
    font-weight: 500;
    color: #64748b !important;
}

/* Active Status Badges */
.badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 9999px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.badge-intent-resolution { background-color: #fee2e2 !important; color: #b91c1c !important; }
.badge-intent-general { background-color: #e0e7ff !important; color: #4338ca !important; }
.badge-intent-unclassified { background-color: #f1f5f9 !important; color: #64748b !important; }

.badge-action-respond { background-color: #dbeafe !important; color: #1e40af !important; }
.badge-action-execute_workflow { background-color: #f3e8ff !important; color: #6b21a8 !important; }
.badge-action-none { background-color: #f1f5f9 !important; color: #64748b !important; }

.badge-status-ready { background-color: #dcfce7 !important; color: #166534 !important; }
.badge-status-waiting_for_user { background-color: #fef3c7 !important; color: #92400e !important; }
.badge-status-completed { background-color: #f3e8ff !important; color: #6b21a8 !important; }
.badge-status-none { background-color: #f1f5f9 !important; color: #64748b !important; }

.badge-escalated { background-color: #fee2e2 !important; color: #b91c1c !important; font-weight: 700; }
.badge-resolved { background-color: #dcfce7 !important; color: #166534 !important; }

.badge-entity {
    background-color: #f1f5f9 !important;
    color: #334155 !important;
    font-family: monospace;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 12px;
}
.entity-list-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
}
</style>
""", unsafe_allow_html=True)

# Premium Header Banner
st.markdown("""
<div class="header-container">
    <h1 class="header-title">Trendly Customer Support Center 🛍️</h1>
    <p class="header-subtitle">Interact with our state-driven customer support assistant in real-time. Follow classifications, workflow statuses, and active session entities in the sidebar.</p>
</div>
""", unsafe_allow_html=True)

# Sidebar controls
st.sidebar.title("Session Controls")
session_id = st.sidebar.text_input("Active Session ID", value="default-session")

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

# Generate badges dynamically
intent_val = session_state['intent'] or 'Unclassified'
intent_badge = f'<span class="badge badge-intent-{intent_val.lower()}">{intent_val}</span>'

action_val = session_state['action'] or 'None'
action_badge = f'<span class="badge badge-action-{action_val.lower()}">{action_val}</span>'

status_val = session_state['workflow_status'] or 'None'
status_badge = f'<span class="badge badge-status-{status_val.lower()}">{status_val}</span>'

missing_val = session_state['missing_entity'] or 'None'
missing_badge = f'<span class="badge-entity">{missing_val}</span>'

reason_val = session_state['reason'] or 'None'

# Render State Card
st.sidebar.markdown(f"""
<div class="state-card">
    <div class="state-row">
        <span class="state-label">Intent</span>
        {intent_badge}
    </div>
    <div class="state-row">
        <span class="state-label">Triage Action</span>
        {action_badge}
    </div>
    <div class="state-row">
        <span class="state-label">Triage Reason</span>
        <span class="badge-entity">{reason_val}</span>
    </div>
    <div class="state-row">
        <span class="state-label">Workflow Status</span>
        {status_badge}
    </div>
    <div class="state-row">
        <span class="state-label">Missing Entity</span>
        {missing_badge}
    </div>
</div>
""", unsafe_allow_html=True)

# Render Resolved Session Entities Card
entities_html = ""
if session_state['entities']:
    for k, v in session_state['entities'].items():
         entities_html += f'<div class="entity-list-item"><span class="state-label">{k}</span><span class="badge-entity">{v}</span></div>'
else:
    entities_html = '<div style="font-size: 13px; color: #94a3b8; font-style: italic;">No active entities.</div>'

st.sidebar.markdown(f"""
<div class="state-card">
    <div style="font-size: 13px; font-weight: 600; color: #1e293b; margin-bottom: 8px; border-bottom: 1px solid #f1f5f9; padding-bottom: 6px;">Resolved Session Entities</div>
    {entities_html}
</div>
""", unsafe_allow_html=True)

# Render Escalation status card if final response exists
if session_state.get("final_response"):
    resp: AgentResponse = session_state["final_response"]
    esc_label = "Escalated" if resp.requires_escalation else "Resolved"
    esc_badge = f'<span class="badge badge-{"escalated" if resp.requires_escalation else "resolved"}">{esc_label}</span>'
    ticket_id_html = f'<div class="state-row"><span class="state-label">Ticket ID</span><span class="badge-entity">{resp.ticket_id}</span></div>' if resp.ticket_id else ""
    st.sidebar.markdown(f"""
    <div class="state-card">
        <div class="state-row">
            <span class="state-label">Escalation Status</span>
            {esc_badge}
        </div>
        {ticket_id_html}
    </div>
    """, unsafe_allow_html=True)

if st.sidebar.button("Reset Session / Clear History", use_container_width=True):
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
if prompt := st.chat_input("How can I help you today?"):
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
