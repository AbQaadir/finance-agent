# Architecture Reference: Salon Payments Ops Agent

**Google ADK on Cloud Run | NVIDIA NeMo Guardrails | Version 1.1**

---


## 1. System Topology

```
Customer Browser                     Ops User (Salon Manager)
       │                                        │
       ▼                                        ▼
[Stripe Elements]                     [Approval Service] (Cloud Run)
       │ Token                                  │ Executes approved fixes only
       ▼                                        ▼
[Payments API] (Cloud Run) <──────────> [Stripe API, Test Mode]
       │                                        ▲
       ▼ Webhooks                               │ Read-only queries
[Worker & Event Bus]                            │
       │ Balanced Entries                       │
       ▼                                        │
[Double-Entry Ledger] (Cloud SQL / SQLite)      │
       ▲                                        │
[Recon Engine] (Cloud Run Job) ─────────┐       │
                                        ▼       │
                              [Exceptions Table]│
                                        │       │
                                        ▼       │
                       [NVIDIA NeMo Guardrails Tier]
                       • Input Rails (PII & Injection)
                       • Dialog Rails (Colang 1.0 Flows)
                       • Action Rails (Whitelist & Cap)
                       • Output Rails (Citation Grounding)
                                        │
                                        ▼
                       [ADK Agent Service] (Private Cloud Run)
                       Coordinator ─► Triage ─► Investigator ─► Proposer
                                                   │
                                     create_proposal (only)
                                                   ▼
                                       [Proposals Queue]
```

---

## 2. Core Subsystems

### 2.1 Payments API & Worker
- **Payments API**: Ingests booking deposits, no-show fees, checkout tips, and refund requests. Handles Stripe tokenization references and order-level idempotency keys. Protects incoming customer notes via NeMo Guardrails input rails.
- **Worker**: Consumes verified Stripe webhook events, deduplicates by `event_id`, and posts balanced double-entry ledger entries.

### 2.2 Double-Entry Ledger
- **Strict Invariant**: $\sum \text{Debits} = \sum \text{Credits}$ for all transaction IDs.
- **Minor Integer Units**: Amounts stored as integer cents to eliminate float rounding errors.
- **Tip Split Engine**: Implements the Hamilton-Hare largest remainder method to allocate tips among staff without losing single cents.

### 2.3 Reconciliation Engine
- Deterministic matcher comparing internal ledger records with processor balance transactions.
- Discrepancy classes: `missing_in_ledger`, `missing_in_stripe`, `amount_mismatch`, `duplicate_charge`, `failed_payout`.

### 2.4 NVIDIA NeMo Guardrails Integration (`libs/guardrails/`)
- Sits between the agent service and models/tools, providing runtime governance:
  1. **Input Rails**: Intercepts user inputs, redacts PII, and defangs prompt-injection attacks.
  2. **Dialog Rails (Colang)**: Scripted conversational paths in `rails.co` deterministically refuse off-topic banter and abort direct money-movement attempts.
  3. **Retrieval Rails**: Defends against context poisoning in transaction metadata.
  4. **Action Rails**: Enforces `ALLOWED_TOOLS` default-deny whitelist, type validations, and maximum \$1,000 threshold.
  5. **Output Rails**: Verifies evidence citation grounding against database records and prevents PII leakage before fix proposals are persisted.

### 2.5 Google ADK Agent Service
- **Coordinator Agent**: Routes exceptions through specialized sub-agents.
- **Triage Agent**: Classifies anomaly categories.
- **Investigator Agent**: Gathers evidence citations via read-only inquiry tools.
- **Proposer Agent**: Generates structured proposals with grounded citations.
- **Reporter Agent**: Generates operational summaries and digests.
- **ADK Callbacks Bridged to NeMo Guardrails**:
  - `before_model_callback`: Routed to NeMo Guardrails Input Rail.
  - `before_tool_callback`: Routed to NeMo Guardrails Action Rail.
  - `after_tool_callback`: Routed to NeMo Guardrails Output Rail & Audit Trail.

### 2.6 Approval Service & Restricted Executor
- Holds proposals awaiting human decision (`approved` / `rejected`).
- Verifies that all cited evidence IDs exist in the database.
- Restricted executor performs financial corrections only upon human authorization.

### 2.7 Multi-Pillar Agent Evaluation Framework (`evals/framework/`)
The system integrates an autonomous, multi-tier evaluation framework engineered specifically for high-assurance financial agents:

1. **Pillar 1: Trajectory Accuracy & Graph Verification (`evals/framework/metrics/trajectory.py`)**:
   - Uses `AgentExecutionTracer` to record each tool execution, argument, and latency.
   - Computes Tool Selection Precision, Recall, and F1 Score against gold-standard trajectories.
   - Verifies sequence order validity: asserts investigative inquiry tools precede proposal generation.
   - Detects execution loops and cyclic tool repetition.

2. **Pillar 2: Citation Grounding & Hallucination Defense (`evals/framework/metrics/grounding.py`)**:
   - Enforces 100% database citation grounding: every ID in `proposal.evidence_ids` is queried against the active database state.
   - Computes citation recall and flags any hallucinated or fabricated record IDs.

3. **Pillar 3: Financial Invariant Verification (`evals/framework/metrics/financial.py`)**:
   - Asserts double-entry accounting balance ($\sum \text{Debits} == \sum \text{Credits}$) with non-negative legs.
   - Asserts minor-unit purity: strictly integer cents; float arithmetic is prohibited.
   - Enforces the proposer-only boundary: zero direct money-movement mutations permitted by agents.
   - Asserts the $1,000.00 (`100000` minor units) proposal ceiling.

4. **Pillar 4: Safety, Alignment & Red-Teaming (`evals/framework/metrics/safety.py`)**:
   - Evaluates resilience against prompt injections, ceiling bypasses, role spoofing, and SQL injection payloads.
   - Verifies NeMo Guardrails Input, Dialog, and Action rail defenses.
   - Verifies PII redaction (PAN, emails, phones) in free text and model outputs.

5. **Pillar 5: Reliability & Latency Distribution (`evals/framework/metrics/reliability.py`)**:
   - Computes $\text{pass}^k$ consistency across repeated non-deterministic agent executions ($k \ge 3$).
   - Computes latency percentiles (p50, p90, p99) to detect operational drift.

#### Benchmark Dataset Topology (`evals/datasets/`):
- `core_reconciliation.json` (35 cases): Standard reconciliation exception scenarios.
- `adversarial_redteam.json` (15 cases): Hostile prompt injections, ceiling exploits, and role hijacking.
- `multi_turn_disputes.json` (10 cases): Multi-turn charge dispute and adjustment workflows.
- `edge_boundaries.json` (8 cases): Extreme boundary conditions (zero cents, single-cent rounding, ceiling thresholds).
- **Total**: 68 structured evaluation scenarios across 4 operational modes (`fast`, `full`, `redteam`, `reliability`).
