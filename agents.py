import os
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from models import IntakeOutput
from prompts import INTAKE_SYSTEM_PROMPT
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
