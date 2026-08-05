import time
import json
import traceback
import contextvars
import functools
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from utils.logger import logger, request_id_var

# Trace context
trace_var = contextvars.ContextVar("trace", default=None)


class RequestTrace:
    """Collects metadata about a request's execution path and metrics."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.start_time = time.time()
        self.nodes_executed = []
        self.tools_executed = []
        self.tool_results = []
        self.router_decision = None
        self.final_structured_output = None
        self.final_response = None
        self.intent = None


def set_request_context(request_id: str) -> RequestTrace:
    """Initialize request_id and trace context."""
    request_id_var.set(request_id)
    trace = RequestTrace(request_id)
    trace_var.set(trace)
    return trace


def get_active_trace() -> Optional[RequestTrace]:
    """Retrieve the active request trace."""
    return trace_var.get()


def get_request_id() -> str:
    """Retrieve the current request ID."""
    return request_id_var.get()


def pretty_format(data: Any) -> str:
    """Format Pydantic models or dicts to indented JSON."""
    if isinstance(data, BaseModel):
        return json.dumps(data.model_dump(), indent=2)
    elif isinstance(data, dict):
        try:
            return json.dumps(data, indent=2)
        except Exception:
            return str(data)
    elif isinstance(data, list):
        try:
            return json.dumps([item.model_dump() if isinstance(item, BaseModel) else item for item in data], indent=2)
        except Exception:
            return str(data)
    return str(data)


# -------------------------------------------------------------------
# Callback Handler for LLM Invocations
# -------------------------------------------------------------------

class LangChainObservabilityHandler(BaseCallbackHandler):
    """Callback handler to trace prompt inputs, model latency, and LLM output details."""

    def __init__(self, agent_name: str):
        super().__init__()
        self.agent_name = agent_name
        self.start_time = 0.0

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        **kwargs: Any,
    ) -> Any:
        self.start_time = time.time()
        logger.info("-" * 40)
        logger.info(f"LLM CALL START: {self.agent_name}")
        logger.info("-" * 40)
        
        # Log prompt/messages sent
        for m_list in messages:
            for msg in m_list:
                role = msg.type.upper()
                logger.info(f"  [{role}] {msg.content[:500]}")

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        latency = (time.time() - self.start_time) * 1000
        logger.info("-" * 40)
        logger.info(f"LLM CALL END: {self.agent_name} (Latency: {latency:.2f}ms)")
        logger.info("-" * 40)
        
        for generation_list in response.generations:
            for gen in generation_list:
                text = gen.text
                logger.info("  [OUTPUT]")
                logger.info(text)
                
                # Check for tool calls inside message info
                message = getattr(gen, "message", None)
                if message and hasattr(message, "tool_calls") and message.tool_calls:
                    logger.info("  [TOOL CALLS CHOSEN]")
                    for tool_call in message.tool_calls:
                        logger.info(f"    Name: {tool_call['name']}")
                        logger.info(f"    Args: {pretty_format(tool_call['args'])}")


# -------------------------------------------------------------------
# Decorators for Nodes, Tools, and Services
# -------------------------------------------------------------------

def trace_node(node_name: str):
    """Decorator to log node execution entry, exit, state mutation, and latency."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(state: Any, *args, **kwargs):
            # Propagate Request ID from graph state to contextvar
            req_id = state.get("request_id") if isinstance(state, dict) else getattr(state, "request_id", None)
            if req_id:
                request_id_var.set(req_id)

            trace = get_active_trace()
            if trace:
                trace.nodes_executed.append(node_name)

            logger.info(f"--------------------------------")
            logger.info(f"NODE: {node_name} - Entering")
            logger.info(f"--------------------------------")
            logger.info("Input State:")
            logger.info(pretty_format(state))

            start = time.time()
            try:
                output = func(state, *args, **kwargs)
                duration = (time.time() - start) * 1000

                logger.info(f"--------------------------------")
                logger.info(f"NODE: {node_name} - Leaving (Time: {duration:.2f}ms)")
                logger.info(f"--------------------------------")
                logger.info("Output State:")
                logger.info(pretty_format(output))
                
                # Record router decision if this was the router node
                if node_name.lower() == "router" and trace and isinstance(output, dict):
                    trace.router_decision = output.get("intent")
                    trace.intent = output.get("intent")
                
                # Record final structured response if populated
                if trace and isinstance(output, dict) and output.get("final_response"):
                    trace.final_structured_output = output.get("final_response")
                    trace.final_response = output.get("final_response").message

                return output
            except Exception as e:
                logger.error(f"!!! EXCEPTION IN NODE {node_name} !!!")
                logger.error(f"Input State:\n{pretty_format(state)}")
                logger.error(f"Exception: {e}")
                logger.error(traceback.format_exc())
                raise e
        return wrapper
    return decorator


def trace_tool(tool_name: str):
    """Decorator to log details about tool inputs, execution parameters, results, and duration."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Parse arguments
            bound_args = {}
            if args:
                bound_args["args"] = args
            bound_args.update(kwargs)

            trace = get_active_trace()
            if trace:
                trace.tools_executed.append(tool_name)

            # Specific tool header formats
            logger.info("====================================")
            logger.info(f"TOOL START: {tool_name.upper()}")
            logger.info("====================================")
            logger.info("Incoming request parameters:")
            logger.info(pretty_format(bound_args))

            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start) * 1000

                logger.info("====================================")
                logger.info(f"TOOL END: {tool_name.upper()} (Time: {duration:.2f}ms)")
                logger.info("====================================")
                logger.info("Returned response:")
                logger.info(pretty_format(result))

                if trace:
                    trace.tool_results.append({
                        "tool": tool_name,
                        "inputs": bound_args,
                        "result": result,
                        "duration_ms": duration
                    })

                return result
            except Exception as e:
                logger.error(f"!!! EXCEPTION IN TOOL {tool_name} !!!")
                logger.error(f"Inputs:\n{pretty_format(bound_args)}")
                logger.error(f"Exception: {e}")
                logger.error(traceback.format_exc())
                raise e
        return wrapper
    return decorator


def trace_service(service_name: str):
    """Decorator to log service inputs, decisions, matches found, and output summaries."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            logger.info(f"[{service_name}] Executing method '{func.__name__}'")
            logger.info(f"[{service_name}] Input received: {args} {kwargs}")

            start = time.time()
            try:
                result = func(self, *args, **kwargs)
                duration = (time.time() - start) * 1000

                logger.info(f"[{service_name}] Method '{func.__name__}' output returned (Time: {duration:.2f}ms):")
                logger.info(pretty_format(result))
                return result
            except Exception as e:
                logger.error(f"!!! EXCEPTION IN SERVICE {service_name}.{func.__name__} !!!")
                logger.error(f"Args: {args} | Kwargs: {kwargs}")
                logger.error(f"Exception: {e}")
                logger.error(traceback.format_exc())
                raise e
        return wrapper
    return decorator
