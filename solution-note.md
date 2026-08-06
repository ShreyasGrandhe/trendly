# Solution Note

# Architecture

The solution is built using **LangGraph** with a **state-driven workflow** for customer support. The application separates the responsibilities of intent understanding, workflow orchestration, data retrieval, and policy reasoning into independent components, making the system modular, maintainable, and easier to extend.

The conversation begins with an **Intake Node**, which:

- Identifies the customer's intent.
- Determines whether sufficient information has been provided.
- Either responds immediately (for greetings or requests missing information) or routes the request to the appropriate workflow.

The application maintains a **persistent conversation state** containing:

- Current workflow
- Extracted entities (such as **Order ID**)
- Workflow status

Instead of reclassifying every user message, subsequent turns simply update any missing information and continue the existing workflow. This makes multi-turn conversations more reliable and prevents loss of conversational context.

For customer queries, the workflows deterministically retrieve only the required business data through dedicated tools:

- **Order Lookup**
- **Policy Lookup**

Once the necessary context has been retrieved, a **single LLM invocation** generates the final customer response using structured outputs. This minimizes unnecessary reasoning, reduces latency, and keeps execution predictable.

The system also integrates **LangSmith tracing** for observability, providing end-to-end visibility into:

- Routing decisions
- Tool execution
- Latency
- Structured outputs

---

# Key Trade-offs

## 1. Deterministic Orchestration vs. Autonomous Agents

Tool execution is controlled by the workflow rather than the LLM.

**Advantages**

- Lower latency
- Eliminates duplicate tool calls
- Predictable execution

**Trade-off**

- Less flexible than a fully autonomous agent capable of dynamic planning.

---

## 2. Persistent Workflow State

Maintaining conversation state increases implementation complexity.

**Advantages**

- Reliable multi-turn conversations
- Seamless workflow continuation
- Improved context retention

---

## 3. Compact Context

Only relevant order information and policy sections are passed to the LLM instead of complete datasets.

**Benefits**

- Lower token consumption
- Faster response generation
- Reduced hallucination risk

---

## 4. Structured Outputs

All LLM responses follow predefined schemas.

**Benefits**

- Improved reliability
- Easier debugging
- Simpler testing
- Deterministic workflow routing

**Trade-off**

- Requires additional schema design and validation.

---

# Known Limitations

- Conversation state is currently stored **in memory**, making it unsuitable for production-scale deployments without persistent storage such as **Redis** or a database.
- Orders and policies are loaded from **static files**. A production implementation would integrate with live **Order Management Systems (OMS)**, **Warehouse Management Systems (WMS)**, and **CRM** platforms.
- Policy retrieval is **rule-based** and assumes well-structured policy documents. Frequently changing or highly complex policies may require semantic retrieval, version management, or a dedicated knowledge base.
- The current implementation focuses on a limited set of customer support workflows. Additional business capabilities such as **payments**, **billing**, **loyalty programs**, and **subscriptions** would require further workflow extensions.

---

# Discovery Questions for Trendly's Operations Team

## 1. Response Time Expectations

What is the acceptable response time for an AI-generated reply?

For example:

- Under **3 seconds** for general support queries.
- Under **5 seconds** for policy-based decisions.

---

## 2. Authentication & Authorization

What authentication or authorization checks are required before exposing customer order details?

---

## 3. Human Escalation Rules

Which customer scenarios must always be escalated to a human support agent?

Understanding mandatory escalation rules helps define appropriate workflow boundaries.

---

## 4. Policy Override Rules

Are there situations where support agents are allowed to override company policies?

The AI needs to understand whether policies are **absolute** or **discretionary**.

---

## 5. Backend System Integrations

Which internal systems or APIs will the assistant need access to?

Examples include:

- Order Management System (OMS)
- Warehouse Management System (WMS)
- Customer Relationship Management (CRM)
- Enterprise Resource Planning (ERP)
- Shipping APIs
- Payment Gateway APIs

---

## 6. Conversation Memory

Should the AI remember context across multiple customer conversations, or only within a single support session?
