---
name: investigate-exception
description: Investigate a payment reconciliation exception across the double-entry ledger and Stripe processor records, and verify grounded proposal citations.
argument-hint: "[exception_id]"
---

# Investigate Reconciliation Exception

Target exception: `$ARGUMENTS`

1. **Inspect Exception Record**:
   - Look up the exception details via `get_exception_details` in `services/agent_service/tools.py` or query `ExceptionRecord` in the database.
   - Identify `kind` (`missing_in_ledger`, `missing_in_stripe`, `amount_mismatch`, `duplicate_charge`, or `failed_payout`), `delta_minor`, `ledger_ref`, and `stripe_ref`.
2. **Cross-Reference Evidence**:
   - Check internal ledger entries (`get_ledger_entry`) and verify `sum(debit_minor) == sum(credit_minor)`.
   - Check Stripe payment/balance status (`get_stripe_transaction`) and webhook audit history (`get_event_history`).
3. **Validate Expected Proposal Mapping**:
   - `missing_in_ledger` -> `post_ledger_adjustment`
   - `missing_in_stripe` -> `post_ledger_adjustment`
   - `amount_mismatch` -> `post_ledger_adjustment`
   - `duplicate_charge` -> `refund_customer`
   - `failed_payout` -> `retry_payout`
4. **Verify Guardrails**:
   - Confirm `amount_minor <= 100000` (`MAX_PROPOSAL_AMOUNT_MINOR`).
   - Confirm every ID in `evidence_ids` resolves to a real database row.
