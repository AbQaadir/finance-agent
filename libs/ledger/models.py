"""
SQLAlchemy models for the Salon Payments Ops double-entry ledger and operational tables.
"""

from datetime import datetime, timezone
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Integer,
    DateTime,
    ForeignKey,
    JSON,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    salon_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # deposit, no_show, tip, checkout
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="usd")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending, paid, refunded, cancelled
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="order")
    tip_splits: Mapped[List["TipSplit"]] = relationship("TipSplit", back_populates="order")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.id"), nullable=False, index=True)
    stripe_payment_intent_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # succeeded, failed, refunded
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="usd")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    order: Mapped["Order"] = relationship("Order", back_populates="payments")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    txn_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Allowed accounts: customer_deposits, salon_revenue, tip_liability, processing_fees, stripe_clearing
    account: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    debit_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="usd")
    source_event_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        CheckConstraint("debit_minor >= 0", name="chk_debit_non_negative"),
        CheckConstraint("credit_minor >= 0", name="chk_credit_non_negative"),
        CheckConstraint("(debit_minor > 0 AND credit_minor = 0) OR (credit_minor > 0 AND debit_minor = 0)", name="chk_debit_xor_credit"),
        Index("idx_ledger_txn_account", "txn_id", "account"),
    )


class TipSplit(Base):
    __tablename__ = "tip_splits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.id"), nullable=False, index=True)
    staff_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    order: Mapped["Order"] = relationship("Order", back_populates="tip_splits")


class StripeEvent(Base):
    __tablename__ = "stripe_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ExceptionRecord(Base):
    __tablename__ = "exceptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # missing_in_ledger, missing_in_stripe, amount_mismatch, duplicate_charge, failed_payout, fee_discrepancy
    ledger_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    stripe_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    delta_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)  # open, under_investigation, proposed, resolved, dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    proposals: Mapped[List["Proposal"]] = relationship("Proposal", back_populates="exception_record")


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    exception_id: Mapped[str] = mapped_column(String(64), ForeignKey("exceptions.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # refund_customer, post_ledger_adjustment, retry_payout, ignore_rounding
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(String(1024), nullable=False)
    evidence_ids: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)  # pending, approved, rejected, executed
    decision_notes: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    exception_record: Mapped["ExceptionRecord"] = relationship("ExceptionRecord", back_populates="proposals")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # agent:triage, agent:investigator, agent:proposer, human:ops, system:worker
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # tool_call, proposal_created, approved, rejected, executed
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
