# Trendly Customer Support AI Assistant

An AI-powered customer support assistant built using **LangGraph**, **FastAPI**, and **Google Gemini**. The assistant helps customers with shipping, tracking, returns, refunds, exchanges, and policy-related queries while combining deterministic workflows with LLM reasoning.

---

## Features

- Intent detection and request triage
- Multi-turn conversations with persistent state
- Order lookup by Order ID
- Policy-aware responses grounded in Trendly's policies
- Return, refund, exchange, and damaged-item resolution
- Deterministic workflow orchestration
- Structured LLM outputs
- LangSmith tracing and observability
- Human escalation for unsupported scenarios

---

## Tech Stack

- Python 3.11+
- LangGraph
- LangChain
- Google Gemini
- FastAPI
- Streamlit
- Pydantic
- LangSmith
- python-dotenv

---

## Project Structure

```text
.
├── app.py                  # FastAPI application
├── graph.py                # LangGraph workflow
├── agents.py               # LLM initialization
├── prompts.py              # System prompts
├── models.py               # Pydantic models
├── tools.py                # LangChain tools
├── services.py             # Business logic & data retrieval
├── ui.py                   # Streamlit frontend
├── data/
│   ├── orders.json
│   └── policy.md
├── utils/
│   ├── logger.py
│   └── observability.py
├── requirements.txt
├── README.md
└── PROMPTS.md
```

---

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd trendly-support-agent
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it

Windows

```bash
.venv\Scripts\activate
```

macOS / Linux

```bash
source .venv/bin/activate
```

---

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Configure environment variables

Create a `.env` file.

```env
GEMINI_API_KEY=YOUR_API_KEY

LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=YOUR_LANGSMITH_KEY
LANGCHAIN_PROJECT=Trendly Support Agent
```

---

## Running the Application

### Option 1 — Streamlit UI (Recommended)

```bash
streamlit run ui.py
```

The application will open in your browser.

---

### Option 2 — FastAPI

Start the backend

```bash
uvicorn app:app --reload
```

Base URL

```
http://127.0.0.1:8000
```

Swagger Documentation

```
http://127.0.0.1:8000/docs
```

---

## API

### POST `/chat`

Request

```json
{
    "session_id": "user-1",
    "message": "Where is my order TR-4525?"
}
```

Response

```json
{
    "response": "...",
    "requires_escalation": false,
    "ticket_id": null
}
```

---

## Example Queries

### General Support

- What are your shipping charges?
- How long does delivery take?
- What is your return window?
- Where is my order TR-4525?

### Resolution

- I want to return TR-4530.
- My order arrived damaged.
- I received the wrong item.
- Can I exchange the size of TR-4528?
- I need a refund.

---

## AI Usage

The application uses Large Language Models only for tasks requiring natural language understanding or policy reasoning.

LLMs are responsible for:

- Customer intent classification
- Multi-turn conversation handling
- Policy interpretation
- Customer response generation

Business data retrieval, workflow routing, and tool execution are deterministic and handled outside the LLM.

This design reduces hallucinations, improves observability, and keeps execution predictable.

---

## Observability

The application integrates with **LangSmith** for tracing and debugging.

Each request logs:

- Request ID
- Workflow executed
- Routing decisions
- Tool executions
- Structured outputs
- Latency

This makes every conversation fully traceable.

---

## Assumptions

- Orders are loaded from the provided JSON dataset.
- Policies are loaded from the supplied Trendly policy document.
- The assistant only answers Trendly-related queries.
- Requests outside the supported domain are politely declined.
- Customer authentication is simulated for assignment purposes.

---

## Future Improvements

- Persistent database-backed sessions
- OMS and CRM integrations
- Semantic policy retrieval
- Authentication and authorization
- Real-time shipment tracking
- Production deployment with Redis and PostgreSQL

---

## Prompt Design

Prompt design and prompt engineering decisions are documented separately in **PROMPTS.md**.

---

## License

This project was developed as part of the Trendly Founding AI Engineer assignment.
