"""
Custom NeMo Guardrails actions for financial safety, policy enforcement, and citation grounding.
"""

from typing import Dict, Any, List, Optional
from nemoguardrails.actions import action
from sqlalchemy import select

from libs.policy.rules import validate_tool_call, PolicyViolation
from libs.redaction.sanitizer import redact_pii, sanitize_free_text, scrub_dict_pii
from libs.ledger.engine import get_db_session
from libs.ledger.models import ExceptionRecord, Payment, LedgerEntry, Order


@action(name="check_pii_action")
def check_pii_action(text: str) -> str:
    """
    Input/Output rail action: Redacts identifiable emails, phone numbers, card numbers, and SSNs.
    """
    if not text:
        return ""
    return redact_pii(text)


@action(name="check_prompt_injection_action")
def check_prompt_injection_action(text: str) -> str:
    """
    Input rail action: Defangs injection attacks and neutralizes malicious instruction resets.
    """
    if not text:
        return ""
    return sanitize_free_text(text)


@action(name="validate_tool_call_action")
def validate_tool_call_action(tool_name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execution/Action rail action: Enforces default-deny policy, tool whitelist,
    and $1,000 maximum amount threshold.
    """
    tool_args = args or {}
    try:
        validate_tool_call(tool_name, tool_args)
        return {"allowed": True, "tool_name": tool_name}
    except PolicyViolation as exc:
        return {"allowed": False, "tool_name": tool_name, "error": str(exc)}


@action(name="verify_citation_grounding_action")
def verify_citation_grounding_action(evidence_ids: List[str], exception_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Output rail action: Verifies that cited record IDs exist in actual database records.
    Prevents hallucinated references from reaching human approval queue.
    """
    if not evidence_ids:
        return {"grounded": False, "error": "Evidence IDs list must not be empty."}

    unverified = []
    with get_db_session() as session:
        exc = session.scalar(select(ExceptionRecord).where(ExceptionRecord.id == exception_id)) if exception_id else None

        for ev_id in evidence_ids:
            found = False
            # Check against current exception references
            if exc and ev_id in (exc.id, exc.ledger_ref, exc.stripe_ref):
                found = True
            elif session.scalar(select(ExceptionRecord).where(ExceptionRecord.id == ev_id)):
                found = True
            elif session.scalar(select(Payment).where((Payment.id == ev_id) | (Payment.stripe_payment_intent_id == ev_id))):
                found = True
            elif session.scalar(select(LedgerEntry).where((LedgerEntry.id == ev_id) | (LedgerEntry.txn_id == ev_id))):
                found = True
            elif session.scalar(select(Order).where(Order.id == ev_id)):
                found = True

            if not found:
                unverified.append(ev_id)

    if unverified:
        return {
            "grounded": False,
            "error": f"Citation verification failure: Evidence IDs {unverified} do not exist in ledger records.",
            "unverified_ids": unverified,
        }

    return {"grounded": True, "verified_count": len(evidence_ids)}
