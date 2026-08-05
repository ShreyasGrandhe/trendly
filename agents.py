import os
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from models import IntakeOutput, AgentResponse
from prompts import (
    INTAKE_SYSTEM_PROMPT,
    GENERAL_SUPPORT_SYSTEM_PROMPT,
    RESOLUTION_SYSTEM_PROMPT,
)
from tools import order_lookup, policy_lookup, escalate
from utils.observability import LangChainObservabilityHandler

# Dynamically resolve model settings from the environment
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai")


def create_intake_agent():
    """Create the Triage/Intake agent."""
    model = init_chat_model(
        MODEL_NAME,
        model_provider=MODEL_PROVIDER,
        temperature=0,
        callbacks=[LangChainObservabilityHandler("Intake Agent")]
    )
    return create_agent(
        model=model,
        tools=[],
        system_prompt=INTAKE_SYSTEM_PROMPT,
        response_format=IntakeOutput,
        name="intake_agent"
    )


def create_general_support_agent():
    """Create the General Support agent."""
    model = init_chat_model(
        MODEL_NAME,
        model_provider=MODEL_PROVIDER,
        temperature=0,
        callbacks=[LangChainObservabilityHandler("General Support Agent")]
    )
    return create_agent(
        model=model,
        tools=[order_lookup, policy_lookup, escalate],
        system_prompt=GENERAL_SUPPORT_SYSTEM_PROMPT,
        response_format=AgentResponse,
        name="general_support_agent"
    )


def create_resolution_agent():
    """Create the Returns & Resolution agent."""
    model = init_chat_model(
        MODEL_NAME,
        model_provider=MODEL_PROVIDER,
        temperature=0,
        callbacks=[LangChainObservabilityHandler("Resolution Agent")]
    )
    return create_agent(
        model=model,
        tools=[order_lookup, policy_lookup, escalate],
        system_prompt=RESOLUTION_SYSTEM_PROMPT,
        response_format=AgentResponse,
        name="resolution_agent"
    )
