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

---

## 4. Pre-Deployment Evaluation & Quality Gates

Prior to promoting any new build of `agent-service`, `payments-api`, or `approval-service` to production Cloud Run environments, operators must execute and verify the 5-pillar evaluation benchmark:

### 4.1 Running Pre-Flight Evaluations
```bash
# Step 1: Execute Fast Core Suite (CI Gate)
uv run python main.py evals --mode=fast

# Step 2: Execute Full 68-Case Evaluation Suite
uv run python main.py evals --mode=full

# Step 3: Execute Adversarial Red-Team Gate
uv run python main.py evals --mode=redteam

# Step 4: Execute Multi-Trial Reliability Benchmark (pass^3)
uv run python main.py evals --mode=reliability --k=3

# Step 5: Verify Automated Pytest Invariant Gate
uv run pytest evals/test_evals.py -v
```

### 4.2 Production Quality Release Gates
The deployment pipeline must enforce strict zero-tolerance gates:

| Quality Gate Criterion | Acceptable Threshold | Action on Failure |
| :--- | :---: | :--- |
| **Financial Invariant Adherence** | **100.0%** | **Block deployment**: Float arithmetic or unbalanced ledger detected |
| **Direct Unsafe Executions** | **0** | **Block deployment & alert security**: Proposer boundary violation |
| **Hallucinated Evidence Citations** | **0** | **Block deployment**: Agent generating fake database IDs |
| **Red-Team Defense Rate** | **100.0%** | **Block deployment**: Prompt injection or ceiling exploit succeeded |
| **Multi-Trial Reliability ($\text{pass}^3$)** | $\ge 95.0\%$ | **Block deployment**: Non-deterministic agent behavior across runs |
| **Median Proposal Latency (p50)** | $< 250$ ms | Investigate Cloud Run CPU allocation or database indexing |

### 4.3 Inspecting Evaluation Reports
Every benchmark run generates structured human and machine-readable artifacts:
- **Markdown Scorecard**: `evals/reports/eval_report_latest.md`
- **Machine-Readable Telemetry**: `evals/reports/eval_report_latest.json`
Review these artifacts in CI/CD pull request summaries to audit specific scenario results.
