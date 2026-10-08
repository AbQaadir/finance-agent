"""
Stripe client adapter supporting both live Stripe API (test mode) and hermetic synthetic mocking.
"""

import os
import uuid
from typing import Dict, Any, Optional

STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "sk_test_synthetic_salon_key")
USE_MOCK_STRIPE = os.getenv("USE_MOCK_STRIPE", "true").lower() == "true" or STRIPE_API_KEY.startswith("sk_test_synthetic")


class StripeAdapter:
    """Encapsulates Stripe API calls with automatic mock fallbacks for testing."""

    def __init__(self, api_key: str = STRIPE_API_KEY):
        self.api_key = api_key
        self.mock_mode = USE_MOCK_STRIPE
        self._mock_charges: Dict[str, Dict[str, Any]] = {}
        self._mock_refunds: Dict[str, Dict[str, Any]] = {}

    def create_payment_intent(
        self,
        amount_minor: int,
        currency: str = "usd",
        metadata: Optional[Dict[str, str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.mock_mode:
            pi_id = f"pi_mock_{uuid.uuid4().hex[:16]}"
            intent = {
                "id": pi_id,
                "amount": amount_minor,
                "currency": currency.lower(),
                "status": "succeeded",
                "client_secret": f"{pi_id}_secret_{uuid.uuid4().hex[:8]}",
                "metadata": metadata or {},
                "idempotency_key": idempotency_key,
                "fee_minor": int(amount_minor * 0.029) + 30,  # Standard 2.9% + 30c
            }
            self._mock_charges[pi_id] = intent
            return intent

        import stripe
        stripe.api_key = self.api_key
        params: Dict[str, Any] = {
            "amount": amount_minor,
            "currency": currency.lower(),
            "metadata": metadata or {},
        }
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        pi = stripe.PaymentIntent.create(**params, headers=headers)
        return {
            "id": pi.id,
            "amount": pi.amount,
            "currency": pi.currency,
            "status": pi.status,
            "client_secret": pi.client_secret,
            "metadata": dict(pi.metadata or {}),
            "fee_minor": int(amount_minor * 0.029) + 30,
        }

    def create_refund(
        self,
        payment_intent_id: str,
        amount_minor: Optional[int] = None,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.mock_mode:
            ref_id = f"re_mock_{uuid.uuid4().hex[:16]}"
            refund = {
                "id": ref_id,
                "payment_intent": payment_intent_id,
                "amount": amount_minor or 0,
                "status": "succeeded",
                "reason": reason or "requested_by_customer",
                "idempotency_key": idempotency_key,
            }
            self._mock_refunds[ref_id] = refund
            return refund

        import stripe
        stripe.api_key = self.api_key
        params: Dict[str, Any] = {
            "payment_intent": payment_intent_id,
        }
        if amount_minor is not None:
            params["amount"] = amount_minor
        if reason:
            params["reason"] = reason
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        ref = stripe.Refund.create(**params, headers=headers)
        return {
            "id": ref.id,
            "payment_intent": ref.payment_intent,
            "amount": ref.amount,
            "status": ref.status,
            "reason": ref.reason,
        }

    def verify_webhook_signature(
        self,
        payload: bytes,
        sig_header: str,
        secret: str,
    ) -> Dict[str, Any]:
        if self.mock_mode and (sig_header == "mock_signature" or not secret or secret == "whsec_mock"):
            import json
            return json.loads(payload.decode("utf-8"))

        import stripe
        return stripe.Webhook.construct_event(payload, sig_header, secret)


default_stripe_adapter = StripeAdapter()
