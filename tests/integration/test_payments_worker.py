"""
Integration tests for Payments API, Webhooks, and Worker ledger posting.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

from libs.ledger.models import Base, Order, Payment, LedgerEntry, TipSplit, StripeEvent
from services.payments_api.main import app, get_db


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


def test_deposit_and_webhook_flow(client, test_db_session):
    # 1. Create deposit order
    payload = {
        "salon_id": "salon_downtown",
        "amount_minor": 5000,
        "currency": "usd",
        "idempotency_key": "dep_idem_001",
        "customer_note": "Haircut and styling deposit",
    }
    resp = client.post("/v1/orders/deposit", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    order_id = data["order_id"]
    pi_id = data["stripe_payment_intent_id"]
    assert pi_id.startswith("pi_mock_")

    # 2. Simulate Stripe webhook
    event_payload = {
        "id": "evt_dep_001",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": pi_id,
                "amount": 5000,
                "currency": "usd",
                "metadata": {"salon_id": "salon_downtown", "type": "deposit"},
            }
        },
    }
    wh_resp = client.post(
        "/v1/webhooks/stripe",
        json=event_payload,
        headers={"stripe-signature": "mock_signature"},
    )
    assert wh_resp.status_code == 200
    assert wh_resp.json() == {"received": True}

    # Verify ledger entries created and balanced
    entries = test_db_session.scalars(select(LedgerEntry)).all()
    assert len(entries) == 3
    total_debit = sum(e.debit_minor for e in entries)
    total_credit = sum(e.credit_minor for e in entries)
    assert total_debit == 5000
    assert total_credit == 5000


def test_checkout_with_tips_flow(client, test_db_session):
    # 1. Create checkout order with $80 service + $20 tip
    payload = {
        "salon_id": "salon_uptown",
        "base_amount_minor": 8000,
        "tip_amount_minor": 2000,
        "currency": "usd",
        "idempotency_key": "chk_idem_002",
    }
    resp = client.post("/v1/orders/checkout", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    pi_id = data["stripe_payment_intent_id"]

    # 2. Trigger webhook
    event_payload = {
        "id": "evt_chk_002",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": pi_id,
                "amount": 10000,
                "currency": "usd",
                "metadata": {
                    "salon_id": "salon_uptown",
                    "type": "checkout",
                    "base_amount_minor": "8000",
                    "tip_amount_minor": "2000",
                },
            }
        },
    }
    wh_resp = client.post("/v1/webhooks/stripe", json=event_payload)
    assert wh_resp.status_code == 200

    # 3. Verify tip splits recorded
    splits = test_db_session.scalars(select(TipSplit)).all()
    assert len(splits) == 2
    assert sum(s.amount_minor for s in splits) == 2000
    # 70% of 2000 is 1400, 30% is 600
    assert {s.amount_minor for s in splits} == {1400, 600}


def test_webhook_deduplication(client, test_db_session):
    # Deposit flow
    payload = {
        "salon_id": "salon_east",
        "amount_minor": 4000,
        "currency": "usd",
        "idempotency_key": "dep_idem_dedup",
    }
    resp = client.post("/v1/orders/deposit", json=payload)
    pi_id = resp.json()["stripe_payment_intent_id"]

    event_payload = {
        "id": "evt_duplicate_001",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": pi_id,
                "amount": 4000,
                "currency": "usd",
                "metadata": {"type": "deposit"},
            }
        },
    }

    # First send
    client.post("/v1/webhooks/stripe", json=event_payload)
    first_entries_count = len(test_db_session.scalars(select(LedgerEntry)).all())

    # Second send of identical event
    client.post("/v1/webhooks/stripe", json=event_payload)
    second_entries_count = len(test_db_session.scalars(select(LedgerEntry)).all())

    assert first_entries_count == second_entries_count
