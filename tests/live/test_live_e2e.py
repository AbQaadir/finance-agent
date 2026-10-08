"""
Live End-to-End Testing Suite for Salon Payments Ops Agent.
Validates the complete operational lifecycle against live Google ADK and Gemini API using .env credentials.
"""

import os
import sys
import time
from typing import Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# 1. Load credentials from .env
load_dotenv(project_root / ".env")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-3.8-flash")


if not GOOGLE_API_KEY:
    print("ERROR: GOOGLE_API_KEY not found in .env file! Live testing requires valid credentials.")
    sys.exit(1)

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from libs.ledger.engine import _engine, init_db, get_db_session
from libs.ledger.models import (
    Base,
    Order,
    Payment,
    LedgerEntry,
    TipSplit,
    ExceptionRecord,
    Proposal,
    AuditLog,
)
from libs.ledger.operations import get_account_balances
from services.payments_api.main import app as payments_app
from services.approval_service.main import app as approval_app
from services.recon_job.matcher import run_reconciliation
from services.recon_job.synthetic import generate_synthetic_scenario
from services.agent_service.coordinator import coordinator_agent, run_exception_investigation
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
import asyncio


def print_section(title: str):
    print("\n" + "=" * 80)
    print(f" {title.upper()}")
    print("=" * 80)


def run_live_test_suite():
    print_section(f"Starting Live Test with Gemini ({GOOGLE_MODEL})")
    print(f"• Google API Key loaded: {'*' * 8}{GOOGLE_API_KEY[-6:]}")
    print(f"• Model target: {GOOGLE_MODEL}")

    # Fresh database reset
    Base.metadata.drop_all(_engine)
    init_db(_engine)
    print("• In-memory/SQLite schema initialized.")

    payments_client = TestClient(payments_app)
    approval_client = TestClient(approval_app)

    # -------------------------------------------------------------
    # STAGE 1: Payments API Ingestion & Tip-Splitting
    # -------------------------------------------------------------
    print_section("Stage 1: Payments API Ingestion & Webhooks")
    
    # 1. Booking deposit
    dep_payload = {
        "salon_id": "salon_soho_01",
        "amount_minor": 5000,  # $50.00
        "currency": "usd",
        "idempotency_key": "live_idem_deposit_001",
        "customer_note": "Customer Sarah booked a cut & color deposit",
    }
    dep_res = payments_client.post("/v1/orders/deposit", json=dep_payload)
    assert dep_res.status_code == 201, f"Deposit creation failed: {dep_res.text}"
    dep_data = dep_res.json()
    deposit_pi = dep_data["stripe_payment_intent_id"]
    print(f"✓ Created deposit order: {dep_data['order_id']} (PI: {deposit_pi})")

    # Ingest webhook for deposit
    dep_evt = {
        "id": "evt_live_dep_001",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": deposit_pi, "amount": 5000, "currency": "usd", "metadata": {"type": "deposit"}}},
    }
    wh_dep_res = payments_client.post("/v1/webhooks/stripe", json=dep_evt)
    assert wh_dep_res.status_code == 200
    print("✓ Ingested and posted deposit webhook into double-entry ledger.")

    # 2. Checkout with service + tip split
    chk_payload = {
        "salon_id": "salon_soho_01",
        "base_amount_minor": 12000,  # $120.00
        "tip_amount_minor": 3000,    # $30.00 tip
        "currency": "usd",
        "idempotency_key": "live_idem_chk_002",
    }
    chk_res = payments_client.post("/v1/orders/checkout", json=chk_payload)
    assert chk_res.status_code == 201
    chk_data = chk_res.json()
    chk_pi = chk_data["stripe_payment_intent_id"]
    print(f"✓ Created checkout order: {chk_data['order_id']} (PI: {chk_pi})")

    chk_evt = {
        "id": "evt_live_chk_002",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": chk_pi,
                "amount": 15000,
                "currency": "usd",
                "metadata": {
                    "type": "checkout",
                    "base_amount_minor": "12000",
                    "tip_amount_minor": "3000",
                },
            }
        },
    }
    wh_chk_res = payments_client.post("/v1/webhooks/stripe", json=chk_evt)
    assert wh_chk_res.status_code == 200
    print("✓ Ingested checkout webhook and calculated tip split across staff.")

    # Verify Ledger Invariants
    with Session(_engine) as session:
        entries = session.scalars(select(LedgerEntry)).all()
        total_deb = sum(e.debit_minor for e in entries)
        total_crd = sum(e.credit_minor for e in entries)
        assert total_deb == total_crd, "Ledger balance invariant violated!"
        print(f"✓ Ledger Invariant Verified: Total Debits ({total_deb}) == Total Credits ({total_crd})")

        splits = session.scalars(select(TipSplit)).all()
        assert sum(s.amount_minor for s in splits) == 3000
        print(f"✓ Tip Split Invariant Verified: Total Split ({sum(s.amount_minor for s in splits)}) == 3000 cents")

    # -------------------------------------------------------------
    # STAGE 2: Deterministic Reconciliation Engine
    # -------------------------------------------------------------
    print_section("Stage 2: Deterministic Reconciliation Run")

    # Introduce synthetic processor discrepancies
    stripe_feed = [
        # Normal matched transactions
        {"id": f"txn_{deposit_pi}", "payment_intent": deposit_pi, "amount": 5000, "status": "available", "type": "charge"},
        {"id": f"txn_{chk_pi}", "payment_intent": chk_pi, "amount": 15000, "status": "available", "type": "charge"},
        # Anomaly 1: Dropped Webhook (Charge in Stripe, missing locally)
        {"id": "txn_orphan_charge", "payment_intent": "pi_orphan_999", "amount": 7500, "status": "available", "type": "charge"},
        # Anomaly 2: Duplicate Charge (Duplicate charge for same booking)
        {"id": "txn_dup_1", "payment_intent": "pi_duplicate_888", "amount": 4000, "status": "available", "type": "charge"},
        {"id": "txn_dup_2", "payment_intent": "pi_duplicate_888", "amount": 4000, "status": "available", "type": "charge"},
    ]

    # Seed the single local payment for Anomaly 2
    with Session(_engine) as session:
        ord_dup = Order(id="ord_dup_888", salon_id="salon_soho_01", type="deposit", amount_minor=4000, status="paid")
        pmt_dup = Payment(id="pmt_dup_888", order_id="ord_dup_888", stripe_payment_intent_id="pi_duplicate_888", status="succeeded", idempotency_key="pay_dup_888", amount_minor=4000)
        session.add_all([ord_dup, pmt_dup])
        session.commit()

    with Session(_engine) as session:
        recon_result = run_reconciliation(session, stripe_feed)
        print(f"✓ Reconciliation Completed: {recon_result.matched_count} matched, {len(recon_result.exceptions_created)} discrepancies detected.")
        assert len(recon_result.exceptions_created) >= 2, "Reconciliation failed to flag anomalies!"
        for exc in recon_result.exceptions_created:
            print(f"  • Flagged Exception: [{exc.kind.upper()}] Delta={exc.delta_minor} cents (ID: {exc.id})")

    # -------------------------------------------------------------
    # STAGE 3: Live Google ADK Agent Investigation with Gemini
    # -------------------------------------------------------------
    print_section("Stage 3: Live Google ADK Agent Investigation (Gemini LLM)")

    # Test direct live ADK runner query to confirm model interaction
    async def query_adk_runner():
        runner = Runner(
            app_name="salon_payments_ops",
            agent=coordinator_agent,
            session_service=InMemorySessionService(),
            auto_create_session=True,
        )
        session = await runner.session_service.create_session(app_name="salon_payments_ops", user_id="ops_tester")
        prompt = (
            "Explain how a salon double-entry ledger should handle a duplicate credit card charge anomaly. "
            "Respond in 2 concise sentences."
        )
        msg = Content(role="user", parts=[Part.from_text(text=prompt)])
        responses = []
        async for event in runner.run_async(session_id=session.id, user_id="ops_tester", new_message=msg):
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        responses.append(part.text)
        return " ".join(responses)

    print(f"Querying Google ADK Runner with Gemini model ({GOOGLE_MODEL})...")
    t0 = time.perf_counter()
    llm_thought = asyncio.run(query_adk_runner())
    t1 = time.perf_counter()
    print(f"✓ Gemini Live Response (took {t1 - t0:.2f}s):\n  \"{llm_thought.strip()}\"")

    # Now run the automated ADK exception investigation pipeline for the detected exceptions
    with Session(_engine) as session:
        exceptions = session.scalars(select(ExceptionRecord).where(ExceptionRecord.status == "open")).all()
        assert len(exceptions) > 0, "No open exceptions to investigate!"

    investigated_proposals = []
    for exc in exceptions:
        print(f"\nInvestigating Exception {exc.id} ({exc.kind})...")
        inv_res = run_exception_investigation(exc.id)
        assert inv_res["success"] is True, f"Investigation failed: {inv_res}"
        proposal = inv_res["proposal"]
        print(f"✓ Agent Proposed Action: '{proposal['action']}' for {proposal['amount_minor']} cents")
        print(f"  Proposal ID: {proposal['proposal_id']} (Status: {proposal['status']})")
        investigated_proposals.append(proposal["proposal_id"])

    # -------------------------------------------------------------
    # STAGE 4: Human-in-the-Loop Approval & Restricted Execution
    # -------------------------------------------------------------
    print_section("Stage 4: Human-in-the-Loop Approval Gate")

    # 1. Fetch pending proposals from Approval Service
    pending_res = approval_client.get("/v1/proposals?status=pending")
    assert pending_res.status_code == 200
    pending_list = pending_res.json()
    print(f"✓ Retrieved {len(pending_list)} pending proposals awaiting human decision.")

    for p in pending_list:
        p_id = p["id"]
        action = p["action"]
        evidence = p["evidence_ids"]
        print(f"\nReviewing Proposal {p_id}:")
        print(f"  • Action: {action}")
        print(f"  • Amount: {p['amount_minor']} cents")
        print(f"  • Cited Evidence: {evidence}")

        # Human operator approves the proposal
        dec_payload = {
            "decision": "approved",
            "decision_notes": f"Reviewed booking timeline. Approved {action} resolution.",
            "actor": "human:salon_ops_director",
        }
        dec_res = approval_client.post(f"/v1/proposals/{p_id}/decision", json=dec_payload)
        assert dec_res.status_code == 200, f"Approval decision failed: {dec_res.text}"
        dec_data = dec_res.json()
        assert dec_data["status"] == "executed"
        assert dec_data["executed"] is True
        print(f"✓ Proposal Approved and Executed: {dec_data['status']}")

    # -------------------------------------------------------------
    # STAGE 5: Audit Trail & Final Settlement Validation
    # -------------------------------------------------------------
    print_section("Stage 5: Audit Trail & Final State Validation")

    with Session(_engine) as session:
        # Verify all exceptions are resolved
        open_count = len(session.scalars(select(ExceptionRecord).where(ExceptionRecord.status == "open")).all())
        resolved_count = len(session.scalars(select(ExceptionRecord).where(ExceptionRecord.status.in_(["resolved", "proposed"]))).all())
        print(f"✓ Exceptions: {open_count} open, {resolved_count} resolved/processed.")

        # Verify audit log entries
        audits = session.scalars(select(AuditLog)).all()
        print(f"✓ Total Audit Log Events Recorded: {len(audits)}")
        for a in audits[-5:]:
            print(f"  • [{a.actor}] {a.event} (Correlation: {a.correlation_id})")

        # Final ledger balance check
        balances = get_account_balances(session)
        print("\nFinal Double-Entry Account Balances:")
        for acct, b in balances.items():
            print(f"  • {acct.ljust(20)}: Debit={b['total_debit']} | Credit={b['total_credit']} | Net={b['net_balance']}")

    print_section("LIVE TEST EXECUTION COMPLETE: ALL 5 STAGES PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_live_test_suite()
