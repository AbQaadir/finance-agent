---
paths:
  - "services/payments_api/**/*.py"
  - "services/approval_service/**/*.py"
  - "services/worker/**/*.py"
  - "services/recon_job/**/*.py"
  - "services/common/**/*.py"
---

# Services, Webhooks, Reconciliation & Approval Gate Rules

- **Payments API (`services/payments_api/`)**:
  - Verify Stripe webhook signatures before enqueueing or processing events.
  - Enforce `idempotency_key` deduplication on order/payment creation endpoints.
- **Worker (`services/worker/processor.py`)**:
  - Deduplicate incoming Stripe webhook events by `event_id` in `stripe_events` before posting ledger entries.
- **Reconciliation Job (`services/recon_job/`)**:
  - Categorize anomalies strictly into the five canonical `ExceptionRecord.kind` values: `missing_in_ledger`, `missing_in_stripe`, `amount_mismatch`, `duplicate_charge`, `failed_payout`.
- **Approval Service (`services/approval_service/`)**:
  - Never execute a proposal unless `decision == "approved"` by an authenticated human actor and `settings.approval_gate_enabled` is `True`.
  - Re-validate that every ID in `proposal.evidence_ids` exists in the database prior to execution in `executor.py`.
