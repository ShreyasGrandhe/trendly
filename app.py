import os
import time
import traceback
from typing import List, Optional
from uuid import uuid4
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Load environment variables (API keys, LangSmith settings)
load_dotenv()

# Explicitly ensure LangSmith env vars are set in os.environ so LangChain picks them up
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "false")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "Trendly Support Agent")
if os.getenv("LANGCHAIN_API_KEY"):
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")

from graph import graph
from models import AgentResponse
from utils.logger import logger
from utils.observability import set_request_context, pretty_format

app = FastAPI(
    title="Trendly Customer Support API",
    version="1.0.0",
)

# Simple in-memory session store for multi-turn conversations
sessions = {}


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    requires_escalation: bool
    ticket_id: Optional[str] = None


@app.get("/")
def health():
    return {"status": "healthy"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    session_id = request.session_id or "default"
    
    # Initialize session if it does not exist
    if session_id not in sessions:
        sessions[session_id] = {
            "messages": [],
            "intent": None,
            "action": None,
            "reason": None,
            "final_response": None,
        }
        
    session_state = sessions[session_id]
    
    # Generate unique Request ID
    request_id = str(uuid4())
    session_state["request_id"] = request_id
    
    # Set Request Context (Request ID & Trace collector)
    trace = set_request_context(request_id)
    
    # Append the new user message
    session_state["messages"].append(HumanMessage(content=request.message))
    
    logger.info(f"API: Received chat request for session '{session_id}' (Message: '{request.message}')")
    
    try:
        # Run the LangGraph workflow, attaching Request ID metadata & tags for LangSmith tracing
        result = graph.invoke(
            session_state,
            config={
                "metadata": {"request_id": request_id},
                "tags": [request_id]
            }
        )
        
        # Persist updated history & intent in the session
        session_state["messages"] = result["messages"]
        session_state["intent"] = result.get("intent")
        session_state["action"] = result.get("action")
        session_state["reason"] = result.get("reason")
        
        # Extract structured response
        final_response: Optional[AgentResponse] = result.get("final_response")
        
        latency_ms = (time.time() - trace.start_time) * 1000
        
        if final_response:
            session_state["final_response"] = final_response
            response_text = final_response.message
            requires_escalation = final_response.requires_escalation
            ticket_id = final_response.ticket_id
        else:
            # Fallback response
            fallback_msg = result["messages"][-1].content if result.get("messages") else "I'm sorry, I encountered an error."
            response_text = fallback_msg
            requires_escalation = False
            ticket_id = None
            
        # Print the Final Execution Summary to console
        logger.info("======================================")
        logger.info("FINAL EXECUTION SUMMARY")
        logger.info("======================================")
        logger.info(f"Request ID: {request_id}")
        logger.info(f"Intent: {result.get('intent')}")
        logger.info(f"Triage Action: {result.get('action')}")
        logger.info(f"Triage Reason: {result.get('reason')}")
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
        
        return ChatResponse(
            response=response_text,
            requires_escalation=requires_escalation,
            ticket_id=ticket_id,
        )
        
    except Exception as e:
        logger.error(f"!!! EXCEPTION OCCURRED DURING APIS LIFE CYCLE !!!")
        logger.error(f"Request ID: {request_id}")
        logger.error(f"Exception: {e}")
        logger.error(traceback.format_exc())
        raise e
