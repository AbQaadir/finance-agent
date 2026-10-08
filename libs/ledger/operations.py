"""
Core double-entry journal operations and ledger query helpers.
Guarantees the fundamental invariant: sum(debits) == sum(credits).
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from .models import (
    LedgerEntry,
    Order,
    Payment,
    TipSplit,
    StripeEvent,
    ExceptionRecord,
    Proposal,
    AuditLog,
)

VALID_ACCOUNTS = {
    "customer_deposits",
    "salon_revenue",
    "tip_liability",
    "processing_fees",
    "stripe_clearing",
}


class LedgerInvariantViolation(ValueError):
    """Raised when journal entries do not balance or violate ledger constraints."""
    pass


def post_journal_entry(
    session: Session,
    txn_id: str,
    entries: List[Dict[str, Any]],
    currency: str = "usd",
    source_event_id: Optional[str] = None,
) -> List[LedgerEntry]:
    """
    Atomically posts a balanced set of double-entry ledger records.
    Each entry dict must contain:
      - account: str (one of VALID_ACCOUNTS)
      - debit_minor: int (>= 0)
      - credit_minor: int (>= 0)
    """
    if not entries:
        raise LedgerInvariantViolation("Cannot post empty journal entry.")

    total_debit = 0
    total_credit = 0
    db_entries: List[LedgerEntry] = []

    for idx, entry in enumerate(entries):
        account = entry.get("account")
        debit = entry.get("debit_minor", 0)
        credit = entry.get("credit_minor", 0)

        if account not in VALID_ACCOUNTS:
            raise LedgerInvariantViolation(
                f"Invalid account '{account}'. Must be one of {sorted(VALID_ACCOUNTS)}"
            )

        if not isinstance(debit, int) or not isinstance(credit, int):
            raise LedgerInvariantViolation("Amounts must be integers in minor units (cents).")

        if debit < 0 or credit < 0:
            raise LedgerInvariantViolation("Debit and credit amounts must be non-negative.")

        if (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
            raise LedgerInvariantViolation(
                f"Entry {idx} for account '{account}' must have either positive debit or positive credit, not both or neither."
            )

        total_debit += debit
        total_credit += credit

        # Only attach source_event_id to the first entry if unique per event
        entry_source = source_event_id if idx == 0 else None

        db_entries.append(
            LedgerEntry(
                txn_id=txn_id,
                account=account,
                debit_minor=debit,
                credit_minor=credit,
                currency=currency.lower(),
                source_event_id=entry_source,
            )
        )

    if total_debit != total_credit:
        raise LedgerInvariantViolation(
            f"Unbalanced journal entry for txn_id '{txn_id}': "
            f"total debit={total_debit} does not equal total credit={total_credit}."
        )

    for record in db_entries:
        session.add(record)

    session.flush()
    return db_entries


def get_account_balances(session: Session, currency: str = "usd") -> Dict[str, Dict[str, int]]:
    """
    Returns total debits, total credits, and net balance (debits - credits) for each account.
    """
    stmt = (
        select(
            LedgerEntry.account,
            func.sum(LedgerEntry.debit_minor).label("total_debit"),
            func.sum(LedgerEntry.credit_minor).label("total_credit"),
        )
        .where(LedgerEntry.currency == currency.lower())
        .group_by(LedgerEntry.account)
    )

    results = session.execute(stmt).all()
    balances = {}
    for row in results:
        deb = int(row.total_debit or 0)
        crd = int(row.total_credit or 0)
        balances[row.account] = {
            "total_debit": deb,
            "total_credit": crd,
            "net_balance": deb - crd,
        }
    return balances


def record_audit(
    session: Session,
    correlation_id: str,
    actor: str,
    event: str,
    details: Dict[str, Any],
) -> AuditLog:
    """Record an audit trail event."""
    log_entry = AuditLog(
        correlation_id=correlation_id,
        actor=actor,
        event=event,
        details=details,
    )
    session.add(log_entry)
    session.flush()
    return log_entry
