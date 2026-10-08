"""
Production entrypoint for the Reconciliation Engine Job.
Can be triggered periodically via Cloud Scheduler on Cloud Run.
"""

import sys
from libs.ledger.engine import get_db_session, init_db
from libs.observability import setup_logger
from services.payments_api.stripe_client import default_stripe_adapter
from .matcher import run_reconciliation

logger = setup_logger("recon-job")


def main():
    logger.info("Starting daily reconciliation job...")
    init_db()

    # In production, pull transactions from Stripe; otherwise use current buffer
    live_txns = default_stripe_adapter.fetch_balance_transactions(limit=100)
    logger.info(f"Retrieved {len(live_txns)} balance transactions from processor feed.")

    with get_db_session() as session:
        result = run_reconciliation(session, live_txns, correlation_id="daily_recon_job")
        logger.info(
            f"Reconciliation completed: {result.matched_count} matched, "
            f"{len(result.exceptions_created)} exceptions created."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
