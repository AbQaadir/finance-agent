"""
Coordinator Agent for Salon Payments Ops.
Orchestrates Triage, Investigator, Proposer, and Reporter sub-agents.
Provides both high-level ADK Runner execution and deterministic workflow fallback.
"""

from typing import Dict, Any, Optional
from google.adk.agents import LlmAgent

from .subagents import (
    triage_agent,
    investigator_agent,
    proposer_agent,
    reporter_agent,
    DEFAULT_MODEL,
)
from .tools import (
    get_exception_details,
    get_ledger_entry,
    get_stripe_transaction,
    create_proposal,
)
from .callbacks import (
    before_model_callback,
    before_tool_callback,
    after_tool_callback,
)

# Root Coordinator Agent
coordinator_agent = LlmAgent(
    name="coordinator_agent",
    model=DEFAULT_MODEL,
    instruction="""You are the Root Coordinator Agent for Salon Payments Ops.
When given an exception ID:
1. Route to triage_agent to classify the anomaly.
2. Route to investigator_agent to gather evidence from the ledger and Stripe.
3. Route to proposer_agent to submit a structured fix proposal to the human approval gate.
Never attempt to execute financial transactions or modify money balances directly.""",
    sub_agents=[
        triage_agent,
        investigator_agent,
        proposer_agent,
        reporter_agent,
    ],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)


def run_exception_investigation(exception_id: str) -> Dict[str, Any]:
    """
    Executes a structured investigation of a reconciliation exception.
    Gathers evidence across ledger and Stripe, formulates appropriate action,
    and calls `create_proposal` (which strictly requires human approval).
    """
    # 1. Fetch exception record
    exc = get_exception_details(exception_id)
    if "error" in exc:
        return {"success": False, "error": exc["error"]}

    kind = exc["kind"]
    delta_minor = exc["delta_minor"]
    ledger_ref = exc.get("ledger_ref")
    stripe_ref = exc.get("stripe_ref")

    evidence_ids = [exception_id]
    if ledger_ref:
        evidence_ids.append(ledger_ref)
    if stripe_ref:
        evidence_ids.append(stripe_ref)

    # 2. Gather evidence
    ledger_data = get_ledger_entry(ledger_ref) if ledger_ref else {}
    stripe_data = get_stripe_transaction(stripe_ref) if stripe_ref else {}

    # 3. Formulate proposal action and justification based on classification
    if kind == "missing_in_ledger":
        action = "post_ledger_adjustment"
        reason = f"Stripe charge '{stripe_ref}' succeeded for {delta_minor} minor units but ledger entry is missing due to a dropped webhook. Post balanced ledger adjustment."
    elif kind == "missing_in_stripe":
        action = "post_ledger_adjustment"
        reason = f"Internal ledger records payment '{ledger_ref}' but Stripe has no record. Reconcile ledger clearing balance."
    elif kind == "amount_mismatch":
        action = "post_ledger_adjustment"
        reason = f"Stripe captured amount differs from ledger entry by {delta_minor} minor units. Post reconciliation delta adjustment."
    elif kind == "duplicate_charge":
        action = "refund_customer"
        reason = f"Detected duplicate Stripe charge for booking payment '{stripe_ref}'. Proposing full refund of {delta_minor} minor units."
    elif kind == "failed_payout":
        action = "retry_payout"
        reason = f"Bank payout failed in Stripe for payout reference '{stripe_ref}'. Retry payout through dashboard."
    else:
        action = "ignore_rounding"
        reason = f"Minor variance of {delta_minor} minor units flagged for operational review."

    # 4. Propose fix (strictly proposes to Approval Service queue; does not move money)
    proposal_result = create_proposal(
        exception_id=exception_id,
        action=action,
        amount_minor=delta_minor,
        reason=reason,
        evidence_ids=evidence_ids,
        confidence=0.95,
    )

    return {
        "success": proposal_result.get("success", False),
        "exception_id": exception_id,
        "classification": kind,
        "proposal": proposal_result,
    }
