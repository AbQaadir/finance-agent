---
paths:
  - "libs/ledger/**/*.py"
  - "libs/tipsplit/**/*.py"
  - "migrations/**/*.py"
---

# Ledger, Accounting & Tip-Split Rules

- **Chart of Accounts**: Only use the canonical accounts defined in `libs/ledger/models.py`:
  - Asset (Debit normal): `stripe_clearing`
  - Expense (Debit normal): `processing_fees`
  - Liabilities (Credit normal): `customer_deposits`, `tip_liability`
  - Revenue (Credit normal): `salon_revenue`
- **Append-Only Journal**: Never issue `UPDATE` or `DELETE` statements against `LedgerEntry`. Corrections and refunds must post new balanced journal entries with a distinct `txn_id` and `source_event_id`.
- **Idempotency**: `Order.idempotency_key`, `Payment.idempotency_key`, and `LedgerEntry.source_event_id` enforce uniqueness. Preserve idempotency checks in `libs/ledger/operations.py`.
- **Hamilton-Hare Tie-Breaking**: In `libs/tipsplit/calculator.py`, when two staff members have identical fractional remainders, tie-break deterministically by original rule index (`-x["idx"]`).
