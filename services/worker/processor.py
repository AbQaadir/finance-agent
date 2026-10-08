"""
Worker event processor for asynchronous Stripe webhook handling and double-entry ledger posting.
Deduplicates events by event_id and guarantees balanced ledger invariant.
"""

import hashlib
import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from libs.ledger.models import (
    Order,
    Payment,
    StripeEvent,
    TipSplit,
)
from libs.ledger.operations import post_journal_entry, record_audit
from libs.tipsplit import split_tips


def process_stripe_event(session: Session, event: Dict[str, Any]) -> bool:
    """
    Idempotently processes a Stripe event and writes double-entry ledger entries.
    Returns True if processed, False if skipped due to deduplication.
    """
    event_id = event.get("id") or event.get("event_id")
    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    if not event_id or not event_type:
        return False

    # 1. Deduplication check
    existing_event = session.scalar(
        select(StripeEvent).where(StripeEvent.event_id == event_id)
    )
    if existing_event:
        return False  # Already processed

    # Compute payload hash
    payload_str = json.dumps(event, sort_keys=True)
    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    # 2. Process according to event type
    if event_type == "payment_intent.succeeded":
        _handle_payment_succeeded(session, event_id, data_object)
    elif event_type in ("charge.refunded", "payment_intent.refunded"):
        _handle_refund(session, event_id, data_object)

    # 3. Mark event as processed
    st_event = StripeEvent(
        event_id=event_id,
        type=event_type,
        payload_hash=payload_hash,
    )
    session.add(st_event)
    session.flush()

    record_audit(
        session=session,
        correlation_id=event_id,
        actor="system:worker",
        event="stripe_event_processed",
        details={"event_id": event_id, "type": event_type},
    )

    return True


def _handle_payment_succeeded(session: Session, event_id: str, data: Dict[str, Any]) -> None:
    pi_id = data.get("id")
    gross_amount = data.get("amount", 0)
    currency = data.get("currency", "usd")
    metadata = data.get("metadata", {})

    payment = session.scalar(
        select(Payment).where(Payment.stripe_payment_intent_id == pi_id)
    )
    if not payment:
        return

    order = session.scalar(select(Order).where(Order.id == payment.order_id))
    if not order:
        return

    payment.status = "succeeded"
    order.status = "paid"

    # Calculate fee (e.g. 2.9% + 30 cents)
    fee_minor = int(gross_amount * 0.029) + 30
    net_clearing = gross_amount - fee_minor
    txn_id = f"txn_{pi_id}"

    if order.type == "deposit":
        entries = [
            {"account": "stripe_clearing", "debit_minor": net_clearing, "credit_minor": 0},
            {"account": "processing_fees", "debit_minor": fee_minor, "credit_minor": 0},
            {"account": "customer_deposits", "debit_minor": 0, "credit_minor": gross_amount},
        ]
        post_journal_entry(session, txn_id=txn_id, entries=entries, currency=currency, source_event_id=event_id)

    elif order.type == "no_show":
        entries = [
            {"account": "stripe_clearing", "debit_minor": net_clearing, "credit_minor": 0},
            {"account": "processing_fees", "debit_minor": fee_minor, "credit_minor": 0},
            {"account": "salon_revenue", "debit_minor": 0, "credit_minor": gross_amount},
        ]
        post_journal_entry(session, txn_id=txn_id, entries=entries, currency=currency, source_event_id=event_id)

    elif order.type == "checkout":
        base_amount = int(metadata.get("base_amount_minor", gross_amount))
        tip_amount = int(metadata.get("tip_amount_minor", 0))

        # Rebalance if necessary
        if base_amount + tip_amount != gross_amount:
            base_amount = gross_amount - tip_amount

        entries = [
            {"account": "stripe_clearing", "debit_minor": net_clearing, "credit_minor": 0},
            {"account": "processing_fees", "debit_minor": fee_minor, "credit_minor": 0},
            {"account": "salon_revenue", "debit_minor": 0, "credit_minor": base_amount},
        ]
        if tip_amount > 0:
            entries.append(
                {"account": "tip_liability", "debit_minor": 0, "credit_minor": tip_amount}
            )

        post_journal_entry(session, txn_id=txn_id, entries=entries, currency=currency, source_event_id=event_id)

        # Distribute tips if rules exist in order/salon
        if tip_amount > 0:
            # Default 70/30 split between lead stylist and assistant if not specified
            default_rules = [
                {"staff_id": "staff_lead_stylist", "basis_points": 7000},
                {"staff_id": "staff_assistant", "basis_points": 3000},
            ]
            splits = split_tips(tip_amount, default_rules)
            for s in splits:
                ts = TipSplit(
                    order_id=order.id,
                    staff_id=s["staff_id"],
                    amount_minor=s["amount_minor"],
                    rule_version="v1",
                )
                session.add(ts)


def _handle_refund(session: Session, event_id: str, data: Dict[str, Any]) -> None:
    pi_id = data.get("payment_intent") or data.get("id")
    refund_amount = data.get("amount", 0)
    currency = data.get("currency", "usd")

    payment = session.scalar(
        select(Payment).where(Payment.stripe_payment_intent_id == pi_id)
    )
    if not payment:
        return

    order = session.scalar(select(Order).where(Order.id == payment.order_id))
    if not order:
        return

    order.status = "refunded"
    payment.status = "refunded"

    # Reverse customer deposit or revenue back out of stripe_clearing
    reversal_account = "customer_deposits" if order.type == "deposit" else "salon_revenue"
    txn_id = f"refund_{pi_id}_{event_id[:8]}"

    entries = [
        {"account": reversal_account, "debit_minor": refund_amount, "credit_minor": 0},
        {"account": "stripe_clearing", "debit_minor": 0, "credit_minor": refund_amount},
    ]
    post_journal_entry(session, txn_id=txn_id, entries=entries, currency=currency, source_event_id=event_id)
