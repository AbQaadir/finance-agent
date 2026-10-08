"""
Unit tests for ADK Agent Service: tools, callbacks, and proposal generation.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from libs.ledger.models import Base, ExceptionRecord, Proposal, Order, Payment
from libs.ledger.engine import _engine
from libs.policy import PolicyViolation
from services.agent_service.tools import (
    get_exception_details,
    create_proposal,
    generate_report,
)
from services.agent_service.callbacks import before_tool_callback
from services.agent_service.coordinator import run_exception_investigation


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(_engine)
    yield


def test_get_exception_details():
    with Session(_engine) as session:
        exc = ExceptionRecord(
            kind="amount_mismatch",
            ledger_ref="led_123",
            stripe_ref="pi_123",
            delta_minor=500,
            status="open",
        )
        session.add(exc)
        session.commit()
        exc_id = exc.id

    details = get_exception_details(exc_id)
    assert details["id"] == exc_id
    assert details["kind"] == "amount_mismatch"
    assert details["delta_minor"] == 500


def test_proposal_rejects_hallucinated_evidence():
    with Session(_engine) as session:
        exc = ExceptionRecord(
            kind="duplicate_charge",
            ledger_ref="led_dup",
            stripe_ref="pi_dup",
            delta_minor=2000,
            status="open",
        )
        session.add(exc)
        session.commit()
        exc_id = exc.id

    # Cite a completely fictional ID
    res = create_proposal(
        exception_id=exc_id,
        action="refund_customer",
        amount_minor=2000,
        reason="Fictional refund",
        evidence_ids=["hallucinated_fake_id_9999"],
    )
    assert res["success"] is False
    assert "Citation verification failure" in res["error"]


def test_proposal_accepts_grounded_evidence():
    with Session(_engine) as session:
        exc = ExceptionRecord(
            kind="duplicate_charge",
            ledger_ref="led_valid",
            stripe_ref="pi_valid",
            delta_minor=2500,
            status="open",
        )
        session.add(exc)
        session.commit()
        exc_id = exc.id

    # Cite valid exception reference
    res = create_proposal(
        exception_id=exc_id,
        action="refund_customer",
        amount_minor=2500,
        reason="Verified duplicate charge on Stripe",
        evidence_ids=[exc_id, "pi_valid"],
        confidence=0.98,
    )
    assert res["success"] is True
    assert res["status"] == "pending"
    assert res["amount_minor"] == 2500


def test_before_tool_callback_enforces_policy():
    class DummyTool:
        name = "transfer_direct_funds"

    with pytest.raises(PolicyViolation, match="not in the allowed tool whitelist"):
        before_tool_callback(DummyTool(), {"amount": 50000}, None)


def test_run_exception_investigation_flow():
    with Session(_engine) as session:
        exc = ExceptionRecord(
            kind="missing_in_ledger",
            stripe_ref="pi_synth_missing_ledger",
            delta_minor=4500,
            status="open",
        )
        session.add(exc)
        session.commit()
        exc_id = exc.id

    inv_res = run_exception_investigation(exc_id)
    assert inv_res["success"] is True
    assert inv_res["classification"] == "missing_in_ledger"
    proposal = inv_res["proposal"]
    assert proposal["action"] == "post_ledger_adjustment"
    assert proposal["amount_minor"] == 4500
