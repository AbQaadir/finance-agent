"""
Restricted Executor for approved proposals.
Holds restricted credentials and performs financial corrections ONLY after human authorization.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from libs.ledger.models import Proposal, ExceptionRecord, LedgerEntry
from libs.ledger.operations import post_journal_entry, record_audit
from services.payments_api.stripe_client import default_stripe_adapter


class ExecutionError(Exception):
    """Raised when proposal execution fails."""
    pass


def execute_approved_proposal(
    session: Session,
    proposal_id: str,
    actor: str = "human:ops_manager",
) -> Dict[str, Any]:
    """
    Executes a previously approved proposal.
    Enforces that status is 'approved' and executes the corresponding financial adjustment.
    """
    proposal = session.scalar(select(Proposal).where(Proposal.id == proposal_id))
    if not proposal:
        raise ExecutionError(f"Proposal {proposal_id} not found.")

    if proposal.status != "approved":
        raise ExecutionError(f"Cannot execute proposal in status '{proposal.status}'. Must be 'approved'.")

    exc = session.scalar(select(ExceptionRecord).where(ExceptionRecord.id == proposal.exception_id))
    action = proposal.action
    amount_minor = proposal.amount_minor

    execution_details: Dict[str, Any] = {"action": action, "amount_minor": amount_minor}

    if action == "refund_customer":
        # Call Stripe refund API via restricted credentials
        stripe_ref = exc.stripe_ref if exc else None
        if not stripe_ref:
            raise ExecutionError("Missing stripe_ref for refund execution.")

        refund_res = default_stripe_adapter.create_refund(
            payment_intent_id=stripe_ref,
            amount_minor=amount_minor,
            reason="requested_by_customer",
            idempotency_key=f"exec_ref_{proposal.id}",
        )
        execution_details["refund_id"] = refund_res.get("id")

        # Post ledger reversal entries
        txn_id = f"exec_adj_{proposal.id}"
        entries = [
            {"account": "salon_revenue", "debit_minor": amount_minor, "credit_minor": 0},
            {"account": "stripe_clearing", "debit_minor": 0, "credit_minor": amount_minor},
        ]
        post_journal_entry(session, txn_id=txn_id, entries=entries)

    elif action == "post_ledger_adjustment":
        # Post balancing adjustment entry in double-entry ledger
        txn_id = f"exec_adj_{proposal.id}"
        entries = [
            {"account": "stripe_clearing", "debit_minor": amount_minor, "credit_minor": 0},
            {"account": "salon_revenue", "debit_minor": 0, "credit_minor": amount_minor},
        ]
        post_journal_entry(session, txn_id=txn_id, entries=entries)

    elif action == "retry_payout":
        execution_details["payout_status"] = "retry_scheduled"

    elif action == "ignore_rounding":
        execution_details["rounding_handled"] = True

    else:
        raise ExecutionError(f"Unknown action: {action}")

    # Mark proposal executed and exception resolved
    proposal.status = "executed"
    if exc:
        exc.status = "resolved" if action != "ignore_rounding" else "dismissed"

    record_audit(
        session=session,
        correlation_id=proposal.id,
        actor=actor,
        event="proposal_executed",
        details=execution_details,
    )

    session.flush()
    return {"success": True, "proposal_id": proposal.id, "execution": execution_details}
