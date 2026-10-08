# Operations Runbook: Salon Payments Ops Agent

Operational guidelines for managing payment workflows, reconciliation exceptions, and human approval gates.

---

## 1. Daily Reconciliation Workflow

1. **Scheduled Execution**:
   - The reconciliation job executes daily at 02:00 UTC via Cloud Scheduler.
   - It performs deterministic matching of internal `ledger_entries` against Stripe balance transactions.
2. **Exception Detection**:
   - Discrepancies are inserted into the `exceptions` table with status `open`.
   - Discrepancy classes:
     - `missing_in_ledger`: Dropped webhook; charge succeeded in Stripe.
     - `missing_in_stripe`: Unsettled transaction recorded locally.
     - `amount_mismatch`: Variance between captured and booked amounts.
     - `duplicate_charge`: Multiple charges for the same order.
     - `failed_payout`: Stripe payout failed to settle in salon bank account.
3. **Agent Investigation**:
   - The ADK Agent Service investigates open exceptions, verifies evidence citations, and submits a proposal to the Approval Service queue with status `pending`.

---

## 2. Reviewing & Deciding Proposals

1. **Viewing Pending Proposals**:
   - Request pending proposals from the Approval Service:
     ```bash
     curl -X GET http://localhost:8000/v1/proposals?status=pending
     ```
2. **Reviewing Grounded Citations**:
   - Verify the `evidence_ids` cited by the agent against the booking timeline and Stripe dashboard.
3. **Recording Decision**:
   - **Approve**:
     ```bash
     curl -X POST http://localhost:8000/v1/proposals/{proposal_id}/decision \
       -H "Content-Type: application/json" \
       -d '{"decision": "approved", "decision_notes": "Verified duplicate charge. Approved refund.", "actor": "human:ops_manager"}'
     ```
     *Approval immediately executes the restricted financial adjustment and marks the proposal `executed` and exception `resolved`.*
   - **Reject**:
     ```bash
     curl -X POST http://localhost:8000/v1/proposals/{proposal_id}/decision \
       -H "Content-Type: application/json" \
       -d '{"decision": "rejected", "decision_notes": "Variance due to in-store cash tip adjustment.", "actor": "human:ops_manager"}'
     ```

---

## 3. Incident Management & Fail-Safe Emergency Freeze

In the event of an anomalous surge in exceptions or suspected prompt-injection campaign:
1. **Freeze Execution Gate**:
   - Set environment variable `APPROVAL_GATE_ENABLED=false` or revoke the restricted Stripe write key in Google Secret Manager.
2. **Audit Inspection**:
   - Query recent audit records:
     ```sql
     SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 50;
     ```
3. **Rollback & Manual Correction**:
   - All ledger entries are append-only. To reverse any erroneous adjustment, post an opposing balanced journal entry with reference to the incident ticket.
