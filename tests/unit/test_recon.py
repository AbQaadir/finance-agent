"""
Tests for deterministic reconciliation matcher and synthetic anomaly detection.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from libs.ledger.models import Base, ExceptionRecord
from services.recon_job.matcher import run_reconciliation
from services.recon_job.synthetic import generate_synthetic_scenario


@pytest.fixture
def recon_db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_clean_match_produces_no_exceptions(recon_db):
    _, _, stripe_txns = generate_synthetic_scenario(recon_db, "clean_match", 5000)
    result = run_reconciliation(recon_db, stripe_txns)
    assert result.matched_count == 1
    assert len(result.exceptions_created) == 0


def test_missing_in_ledger_detected(recon_db):
    _, _, stripe_txns = generate_synthetic_scenario(recon_db, "missing_in_ledger", 7500)
    result = run_reconciliation(recon_db, stripe_txns)
    assert len(result.exceptions_created) == 1
    exc = result.exceptions_created[0]
    assert exc.kind == "missing_in_ledger"
    assert exc.delta_minor == 7500


def test_missing_in_stripe_detected(recon_db):
    _, _, stripe_txns = generate_synthetic_scenario(recon_db, "missing_in_stripe", 6000)
    result = run_reconciliation(recon_db, stripe_txns)
    assert len(result.exceptions_created) == 1
    exc = result.exceptions_created[0]
    assert exc.kind == "missing_in_stripe"
    assert exc.delta_minor == 6000


def test_amount_mismatch_detected(recon_db):
    _, _, stripe_txns = generate_synthetic_scenario(recon_db, "amount_mismatch", 5000)
    result = run_reconciliation(recon_db, stripe_txns)
    assert len(result.exceptions_created) == 1
    exc = result.exceptions_created[0]
    assert exc.kind == "amount_mismatch"
    assert exc.delta_minor == 1000  # $50 vs $40


def test_duplicate_charge_detected(recon_db):
    _, _, stripe_txns = generate_synthetic_scenario(recon_db, "duplicate_charge", 3000)
    result = run_reconciliation(recon_db, stripe_txns)
    assert len(result.exceptions_created) == 1
    exc = result.exceptions_created[0]
    assert exc.kind == "duplicate_charge"
