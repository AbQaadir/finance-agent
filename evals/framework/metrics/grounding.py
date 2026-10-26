"""
Evidence Grounding and Factual Faithfulness Metrics.
Asserts 100% database citation grounding, measures hallucination rate, and verifies evidence completeness.
"""

from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import select

from libs.ledger.models import ExceptionRecord, Payment, LedgerEntry, Order


def verify_citation_exists(evidence_id: str, session: Session, exc: Optional[ExceptionRecord] = None) -> bool:
    """Checks if an evidence ID exists in real database records."""
    if not evidence_id:
        return False

    if exc and evidence_id in (exc.id, exc.ledger_ref, exc.stripe_ref):
        return True

    if session.scalar(select(ExceptionRecord).where(ExceptionRecord.id == evidence_id)):
        return True
    if session.scalar(select(Payment).where((Payment.id == evidence_id) | (Payment.stripe_payment_intent_id == evidence_id))):
        return True
    if session.scalar(select(LedgerEntry).where((LedgerEntry.id == evidence_id) | (LedgerEntry.txn_id == evidence_id))):
        return True
    if session.scalar(select(Order).where(Order.id == evidence_id)):
        return True

    return False


def evaluate_citation_grounding(
    evidence_ids: List[str],
    session: Session,
    exception_id: Optional[str] = None,
    expected_evidence_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Evaluates evidence citations for a proposal:
    - Grounding Rate: Proportion of cited IDs that exist in the database (must be 1.0).
    - Hallucinated Count: Number of invented IDs.
    - Recall: Proportion of expected key IDs that were cited.
    """
    if not evidence_ids:
        return {
            "grounding_rate": 0.0,
            "hallucinated_count": 0,
            "citation_recall": 0.0,
            "is_grounded": False,
            "unverified_ids": [],
            "error": "No evidence cited.",
        }

    exc = session.scalar(select(ExceptionRecord).where(ExceptionRecord.id == exception_id)) if exception_id else None

    unverified_ids: List[str] = []
    verified_ids: List[str] = []

    for ev_id in evidence_ids:
        if verify_citation_exists(ev_id, session, exc):
            verified_ids.append(ev_id)
        else:
            unverified_ids.append(ev_id)

    total_cited = len(evidence_ids)
    grounding_rate = len(verified_ids) / total_cited if total_cited > 0 else 0.0

    # Recall against expected evidence IDs if provided
    recall = 1.0
    if expected_evidence_ids:
        found_expected = set(expected_evidence_ids).intersection(set(verified_ids))
        recall = len(found_expected) / len(expected_evidence_ids) if expected_evidence_ids else 1.0

    return {
        "total_cited": total_cited,
        "verified_count": len(verified_ids),
        "hallucinated_count": len(unverified_ids),
        "grounding_rate": round(grounding_rate, 4),
        "citation_recall": round(recall, 4),
        "is_grounded": len(unverified_ids) == 0 and len(verified_ids) > 0,
        "unverified_ids": unverified_ids,
    }
