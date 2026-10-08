"""
FastAPI Payments API service for Salon Payments Ops.
Handles deposits, no-show fees, checkout tips, refunds, and Stripe webhooks.
"""

from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
import uuid
import os
from fastapi import FastAPI, HTTPException, Header, Request, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select

from libs.ledger.engine import get_db_session, init_db
from libs.ledger.models import Order, Payment, StripeEvent
from libs.redaction.sanitizer import sanitize_free_text
from .stripe_client import default_stripe_adapter, StripeAdapter

WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mock")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Salon Payments API",
    version="0.1.0",
    description="Processes salon deposits, fees, checkout tips, and webhook events.",
    lifespan=lifespan,
)



# Dependency
def get_db():
    with get_db_session() as session:
        yield session


# ===================== SCHEMAS =====================

class DepositRequest(BaseModel):
    salon_id: str
    amount_minor: int = Field(gt=0, description="Deposit amount in minor units (e.g. cents)")
    currency: str = "usd"
    idempotency_key: str
    customer_note: Optional[str] = None


class NoShowRequest(BaseModel):
    salon_id: str
    amount_minor: int = Field(gt=0)
    currency: str = "usd"
    idempotency_key: str
    reason: Optional[str] = "Customer did not show up"


class TipRuleSchema(BaseModel):
    staff_id: str
    basis_points: int


class CheckoutRequest(BaseModel):
    salon_id: str
    base_amount_minor: int = Field(gt=0)
    tip_amount_minor: int = Field(ge=0, default=0)
    tip_rules: List[TipRuleSchema] = []
    currency: str = "usd"
    idempotency_key: str


class RefundRequest(BaseModel):
    amount_minor: Optional[int] = Field(None, gt=0)
    reason: Optional[str] = "requested_by_customer"
    idempotency_key: str


# ===================== ENDPOINTS =====================

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "payments_api"}


@app.post("/v1/orders/deposit", status_code=status.HTTP_201_CREATED)
def create_deposit(req: DepositRequest, db: Session = Depends(get_db)):
    # Order-level idempotency check
    existing_order = db.scalar(
        select(Order).where(Order.idempotency_key == req.idempotency_key)
    )
    if existing_order:
        existing_payment = db.scalar(
            select(Payment).where(Payment.order_id == existing_order.id)
        )
        return {
            "order_id": existing_order.id,
            "status": existing_order.status,
            "amount_minor": existing_order.amount_minor,
            "stripe_payment_intent_id": existing_payment.stripe_payment_intent_id if existing_payment else None,
            "idempotency_replayed": True,
        }

    # Sanitize any free-text notes
    safe_note = sanitize_free_text(req.customer_note) if req.customer_note else ""

    # Create Stripe PaymentIntent
    metadata = {
        "salon_id": req.salon_id,
        "type": "deposit",
        "customer_note": safe_note,
    }
    pi = default_stripe_adapter.create_payment_intent(
        amount_minor=req.amount_minor,
        currency=req.currency,
        metadata=metadata,
        idempotency_key=f"pi_{req.idempotency_key}",
    )

    order = Order(
        salon_id=req.salon_id,
        type="deposit",
        amount_minor=req.amount_minor,
        currency=req.currency,
        status="pending",
        idempotency_key=req.idempotency_key,
    )
    db.add(order)
    db.flush()

    payment = Payment(
        order_id=order.id,
        stripe_payment_intent_id=pi["id"],
        status="pending",
        idempotency_key=f"pay_{req.idempotency_key}",
        amount_minor=req.amount_minor,
        currency=req.currency,
    )
    db.add(payment)
    db.flush()

    return {
        "order_id": order.id,
        "stripe_payment_intent_id": pi["id"],
        "client_secret": pi.get("client_secret"),
        "status": order.status,
        "amount_minor": order.amount_minor,
    }


@app.post("/v1/orders/no-show", status_code=status.HTTP_201_CREATED)
def charge_no_show(req: NoShowRequest, db: Session = Depends(get_db)):
    existing = db.scalar(select(Order).where(Order.idempotency_key == req.idempotency_key))
    if existing:
        return {"order_id": existing.id, "status": existing.status, "idempotency_replayed": True}

    pi = default_stripe_adapter.create_payment_intent(
        amount_minor=req.amount_minor,
        currency=req.currency,
        metadata={"salon_id": req.salon_id, "type": "no_show", "reason": req.reason},
        idempotency_key=f"pi_{req.idempotency_key}",
    )

    order = Order(
        salon_id=req.salon_id,
        type="no_show",
        amount_minor=req.amount_minor,
        currency=req.currency,
        status="pending",
        idempotency_key=req.idempotency_key,
    )
    db.add(order)
    db.flush()

    payment = Payment(
        order_id=order.id,
        stripe_payment_intent_id=pi["id"],
        status="pending",
        idempotency_key=f"pay_{req.idempotency_key}",
        amount_minor=req.amount_minor,
        currency=req.currency,
    )
    db.add(payment)
    db.flush()

    return {
        "order_id": order.id,
        "stripe_payment_intent_id": pi["id"],
        "client_secret": pi.get("client_secret"),
        "amount_minor": order.amount_minor,
    }


@app.post("/v1/orders/checkout", status_code=status.HTTP_201_CREATED)
def checkout_service(req: CheckoutRequest, db: Session = Depends(get_db)):
    existing = db.scalar(select(Order).where(Order.idempotency_key == req.idempotency_key))
    if existing:
        return {"order_id": existing.id, "status": existing.status, "idempotency_replayed": True}

    total_amount = req.base_amount_minor + req.tip_amount_minor
    metadata = {
        "salon_id": req.salon_id,
        "type": "checkout",
        "base_amount_minor": str(req.base_amount_minor),
        "tip_amount_minor": str(req.tip_amount_minor),
    }

    pi = default_stripe_adapter.create_payment_intent(
        amount_minor=total_amount,
        currency=req.currency,
        metadata=metadata,
        idempotency_key=f"pi_{req.idempotency_key}",
    )

    order = Order(
        salon_id=req.salon_id,
        type="checkout",
        amount_minor=total_amount,
        currency=req.currency,
        status="pending",
        idempotency_key=req.idempotency_key,
    )
    db.add(order)
    db.flush()

    payment = Payment(
        order_id=order.id,
        stripe_payment_intent_id=pi["id"],
        status="pending",
        idempotency_key=f"pay_{req.idempotency_key}",
        amount_minor=total_amount,
        currency=req.currency,
    )
    db.add(payment)
    db.flush()

    return {
        "order_id": order.id,
        "stripe_payment_intent_id": pi["id"],
        "client_secret": pi.get("client_secret"),
        "total_amount_minor": total_amount,
        "base_amount_minor": req.base_amount_minor,
        "tip_amount_minor": req.tip_amount_minor,
    }


@app.post("/v1/orders/{order_id}/refund")
def refund_order(order_id: str, req: RefundRequest, db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    payment = db.scalar(select(Payment).where(Payment.order_id == order_id))
    if not payment:
        raise HTTPException(status_code=400, detail="No payment found for order")

    refund_amount = req.amount_minor or payment.amount_minor
    ref = default_stripe_adapter.create_refund(
        payment_intent_id=payment.stripe_payment_intent_id,
        amount_minor=refund_amount,
        reason=req.reason,
        idempotency_key=req.idempotency_key,
    )

    order.status = "refunded"
    payment.status = "refunded"
    db.flush()

    return {
        "refund_id": ref["id"],
        "order_id": order.id,
        "amount_minor": refund_amount,
        "status": "refunded",
    }


@app.post("/v1/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default="mock_signature"),
    db: Session = Depends(get_db),
):
    body = await request.body()
    try:
        event = default_stripe_adapter.verify_webhook_signature(
            payload=body,
            sig_header=stripe_signature,
            secret=WEBHOOK_SECRET,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {str(e)}")

    # Delegate processing to the worker (synchronously for local/test, or via Pub/Sub)
    from services.worker.processor import process_stripe_event
    process_stripe_event(db, event)

    return {"received": True}
