# Prompt Design

This application uses three dedicated prompts, each responsible for a different stage of the customer support workflow. Separating prompts allows each LLM call to focus on a single responsibility, reducing prompt complexity and improving reliability.

---

# 1. Intake & Triage Prompt

## Purpose

The **Intake & Triage Prompt** acts as the entry point for every conversation. Its responsibility is to understand the user's intent and determine the appropriate next action.

## Responsibilities

- Classify the user's request as **General** or **Resolution**.
- Determine whether sufficient information is available to continue.
- Request any missing information (e.g., **Order ID**) before triggering downstream workflows.
- Populate structured routing fields required by the workflow engine.

## Output

The prompt returns structured JSON containing:

- `intent`
- `action`
- `workflow`
- `required_tools`
- `missing_entity`
- `workflow_status`

## Iteration

The initial version only classified requests into **General** and **Resolution** categories. During development, it was extended to support persistent workflow state by returning additional routing metadata such as:

- `workflow`
- `requires_order`
- `requires_policy`
- `missing_entity`

This eliminated repeated intent classification across multi-turn conversations and significantly improved workflow continuity.

---

# 2. General Support Prompt

## Purpose

The **General Support Prompt** handles informational customer support requests that do not require complex policy reasoning.

### Example Requests

- Shipping charges
- Dispatch timelines
- Delivery tracking
- Return window
- General policy questions

## Responsibilities

- Answer only using retrieved order and policy information.
- Never fabricate order details or company policies.
- Present responses in a professional and customer-friendly manner.
- Escalate only when deterministic business rules require human intervention.

## Iteration

Earlier versions allowed the LLM to decide which information should be retrieved. This resulted in unnecessary reasoning and repeated tool calls.

The final design moved tool orchestration into deterministic workflows, allowing the prompt to focus exclusively on interpreting retrieved information and generating the final customer response.

---

# 3. Resolution Prompt

## Purpose

The **Resolution Prompt** handles customer-specific requests that require policy reasoning.

### Example Requests

- Return eligibility
- Refund eligibility
- Exchange requests
- Damaged or defective items
- Lost parcels

## Responsibilities

- Apply Trendly policies to retrieved order information.
- Determine customer eligibility.
- Generate empathetic, policy-compliant responses.
- Identify scenarios requiring escalation.

## Iteration

The initial implementation used a **ReAct-style agent** responsible for selecting tools and performing reasoning. While effective, it introduced additional latency due to repeated planning and tool selection.

The final architecture shifted all information retrieval into deterministic workflows, allowing the prompt to focus solely on policy reasoning and customer communication. This significantly reduced latency while maintaining decision quality.

---

# Overall Prompt Engineering Approach

The prompt architecture follows three core design principles:

## 1. Single Responsibility

Each prompt performs one clearly defined task:

- **Intake & Triage** → Understand and route the request.
- **General Support** → Answer informational queries.
- **Resolution** → Perform policy reasoning and eligibility decisions.

---

## 2. Structured Outputs

Every LLM invocation returns structured data rather than free-form text. This enables:

- Deterministic workflow routing
- Easier debugging
- Better observability
- Reliable multi-turn state management

---

## 3. Retrieval Before Reasoning

Business data is retrieved before invoking the LLM.

Rather than relying on the model's internal knowledge, responses are grounded in:

- Retrieved order information
- Company policies
- Deterministic workflow outputs

This approach minimizes hallucinations while ensuring accurate, policy-compliant customer support responses.
