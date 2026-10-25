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
