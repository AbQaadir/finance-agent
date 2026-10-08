"""
Integration tests for Approval Service: human decision gate and restricted execution.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from libs.ledger.models import Base, Proposal, ExceptionRecord, LedgerEntry
from services.approval_service.main import app, get_db


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield session
    session.close()
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_db_session):
    return TestClient(app)


def test_list_and_approve_proposal(client, test_db_session):
    # 1. Seed exception and proposal
    exc = ExceptionRecord(
        kind="duplicate_charge",
        stripe_ref="pi_dup_test_123",
        delta_minor=3500,
        status="proposed",
    )
    test_db_session.add(exc)
    test_db_session.flush()

    proposal = Proposal(
        exception_id=exc.id,
        action="refund_customer",
        amount_minor=3500,
        reason="Duplicate booking charge detected in Stripe logs.",
        evidence_ids=[exc.id, "pi_dup_test_123"],
        confidence=0.95,
        status="pending",
    )
    test_db_session.add(proposal)
    test_db_session.flush()

    # 2. List proposals
    list_resp = client.get("/v1/proposals?status=pending")
    assert list_resp.status_code == 200
    proposals = list_resp.json()
    assert len(proposals) == 1
    assert proposals[0]["id"] == proposal.id

    # 3. Approve proposal
    dec_resp = client.post(
        f"/v1/proposals/{proposal.id}/decision",
        json={
            "decision": "approved",
            "decision_notes": "Verified with customer booking timeline. Safe to refund.",
            "actor": "human:jane_manager",
        },
    )
    assert dec_resp.status_code == 200
    data = dec_resp.json()
    assert data["status"] == "executed"
    assert data["executed"] is True


    # 4. Verify in DB
    refreshed_p = test_db_session.scalar(select(Proposal).where(Proposal.id == proposal.id))
    assert refreshed_p.status == "executed"
    refreshed_exc = test_db_session.scalar(select(ExceptionRecord).where(ExceptionRecord.id == exc.id))
    assert refreshed_exc.status == "resolved"

    # Verify ledger entries posted by executor
    ledger_entries = test_db_session.scalars(select(LedgerEntry)).all()
    assert len(ledger_entries) == 2
    assert sum(e.debit_minor for e in ledger_entries) == 3500
    assert sum(e.credit_minor for e in ledger_entries) == 3500


def test_reject_proposal(client, test_db_session):
    exc = ExceptionRecord(kind="amount_mismatch", delta_minor=1000, status="proposed")
    test_db_session.add(exc)
    test_db_session.flush()

    proposal = Proposal(
        exception_id=exc.id,
        action="post_ledger_adjustment",
        amount_minor=1000,
        reason="Discrepancy adjustment",
        evidence_ids=[exc.id],
        confidence=0.8,
        status="pending",
    )
    test_db_session.add(proposal)
    test_db_session.flush()

    # Reject
    dec_resp = client.post(
        f"/v1/proposals/{proposal.id}/decision",
        json={
            "decision": "rejected",
            "decision_notes": "Not an error; customer used an in-salon voucher.",
            "actor": "human:john_ops",
        },
    )
    assert dec_resp.status_code == 200
    assert dec_resp.json()["status"] == "rejected"
    assert dec_resp.json()["executed"] is False

    # Check that no ledger adjustment was posted
    ledger_entries = test_db_session.scalars(select(LedgerEntry)).all()
    assert len(ledger_entries) == 0
