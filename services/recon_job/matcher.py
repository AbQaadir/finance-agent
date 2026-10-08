"""
Deterministic reconciliation matcher for Salon Payments Ops.
Compares internal double-entry ledger records with Stripe balance transactions.
Flags anomalies and records them into the exceptions table.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from libs.ledger.models import (
    LedgerEntry,
    Payment,
    Order,
    ExceptionRecord,
)
from libs.ledger.operations import record_audit


class ReconciliationResult:
    def __init__(self):
        self.matched_count: int = 0
        self.exceptions_created: List[ExceptionRecord] = []


def run_reconciliation(
    session: Session,
    stripe_transactions: List[Dict[str, Any]],
    correlation_id: str = "daily_recon",
) -> ReconciliationResult:
    """
    Deterministic matching between internal database payments/ledger and Stripe transactions.
    
    `stripe_transactions` is a list of Stripe balance transactions or charge summaries:
    [
      {
        "id": "txn_stripe_123",
        "payment_intent": "pi_123",
        "amount": 5000,
        "fee": 175,
        "status": "available", # or "failed", "pending"
        "type": "charge" # or "payout"
      }
    ]
    """
    res = ReconciliationResult()

    # Index stripe transactions by payment_intent
    stripe_by_pi: Dict[str, Dict[str, Any]] = {}
    stripe_seen_counts: Dict[str, int] = {}
    for st in stripe_transactions:
        pi = st.get("payment_intent") or st.get("id")
        stripe_by_pi[pi] = st
        stripe_seen_counts[pi] = stripe_seen_counts.get(pi, 0) + 1

    # Fetch all internal payments
    payments = session.scalars(select(Payment)).all()
    internal_pi_set = set()

    for p in payments:
        internal_pi_set.add(p.stripe_payment_intent_id)
        st = stripe_by_pi.get(p.stripe_payment_intent_id)

        # Check: Missing in Stripe
        if not st:
            exc = ExceptionRecord(
                kind="missing_in_stripe",
                ledger_ref=p.id,
                stripe_ref=p.stripe_payment_intent_id,
                delta_minor=p.amount_minor,
                status="open",
            )
            session.add(exc)
            res.exceptions_created.append(exc)
            continue

        # Check: Duplicate charge in Stripe
        if stripe_seen_counts.get(p.stripe_payment_intent_id, 0) > 1:
            exc = ExceptionRecord(
                kind="duplicate_charge",
                ledger_ref=p.id,
                stripe_ref=p.stripe_payment_intent_id,
                delta_minor=st.get("amount", 0),
                status="open",
            )
            session.add(exc)
            res.exceptions_created.append(exc)
            continue

        # Check: Amount mismatch
        stripe_amount = st.get("amount", 0)
        if p.amount_minor != stripe_amount:
            exc = ExceptionRecord(
                kind="amount_mismatch",
                ledger_ref=p.id,
                stripe_ref=p.stripe_payment_intent_id,
                delta_minor=abs(p.amount_minor - stripe_amount),
                status="open",
            )
            session.add(exc)
            res.exceptions_created.append(exc)
            continue

        # Check: Failed payout / status
        if st.get("status") == "failed":
            exc = ExceptionRecord(
                kind="failed_payout",
                ledger_ref=p.id,
                stripe_ref=st.get("id"),
                delta_minor=stripe_amount,
                status="open",
            )
            session.add(exc)
            res.exceptions_created.append(exc)
            continue

        # Matched successfully
        res.matched_count += 1

    # Check: Missing in Ledger (Stripe has charge, but DB has no payment)
    for pi_id, st in stripe_by_pi.items():
        if pi_id not in internal_pi_set and st.get("type") == "charge":
            exc = ExceptionRecord(
                kind="missing_in_ledger",
                ledger_ref=None,
                stripe_ref=pi_id,
                delta_minor=st.get("amount", 0),
                status="open",
            )
            session.add(exc)
            res.exceptions_created.append(exc)

    session.flush()

    record_audit(
        session=session,
        correlation_id=correlation_id,
        actor="system:recon_job",
        event="reconciliation_completed",
        details={
            "matched_count": res.matched_count,
            "exceptions_created": len(res.exceptions_created),
        },
    )
    session.commit()

    return res

