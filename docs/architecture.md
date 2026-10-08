# Architecture Reference: Salon Payments Ops Agent

**Google ADK on Cloud Run | Enterprise Financial Architecture | Version 1.0**

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
- **Payments API**: Ingests booking deposits, no-show fees, checkout tips, and refund requests. Handles Stripe tokenization references and order-level idempotency keys.
- **Worker**: Consumes verified Stripe webhook events, deduplicates by `event_id`, and posts balanced double-entry ledger entries.

### 2.2 Double-Entry Ledger
- **Strict Invariant**: $\sum \text{Debits} = \sum \text{Credits}$ for all transaction IDs.
- **Minor Integer Units**: Amounts stored as integer cents to eliminate float rounding errors.
- **Tip Split Engine**: Implements the Hamilton-Hare largest remainder method to allocate tips among staff without losing single cents.

### 2.3 Reconciliation Engine
- Deterministic matcher comparing internal ledger records with processor balance transactions.
- Discrepancy classes: `missing_in_ledger`, `missing_in_stripe`, `amount_mismatch`, `duplicate_charge`, `failed_payout`.

### 2.4 Google ADK Agent Service
- **Coordinator Agent**: Routes exceptions through specialized sub-agents.
- **Triage Agent**: Classifies anomaly categories.
- **Investigator Agent**: Gathers evidence citations via read-only inquiry tools.
- **Proposer Agent**: Generates structured proposals with grounded citations.
- **Reporter Agent**: Generates operational summaries and digests.
- **ADK Callbacks**:
  - `before_model_callback`: PII scrubbing and prompt sanitization.
  - `before_tool_callback`: Default-deny policy and amount limit verification.
  - `after_tool_callback`: Audit trail logging.

### 2.5 Approval Service & Restricted Executor
- Holds proposals awaiting human decision (`approved` / `rejected`).
- Verifies that all cited evidence IDs exist in the database.
- Restricted executor performs financial corrections only upon human authorization.
