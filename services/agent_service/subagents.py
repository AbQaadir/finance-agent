"""
ADK Sub-agents for Triage, Investigation, Proposal, and Reporting.
Each agent has a strictly scoped single responsibility and minimal tool surface.
"""

import os
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

load_dotenv()

from .tools import (
    get_exception_details,
    get_ledger_entry,
    get_stripe_transaction,
    get_event_history,
    create_proposal,
    generate_report,
)
from .callbacks import (
    before_model_callback,
    before_tool_callback,
    after_tool_callback,
)

DEFAULT_MODEL = os.getenv("GOOGLE_MODEL", "gemini-3.8-flash")


# ===================== 1. TRIAGE AGENT =====================
triage_agent = LlmAgent(
    name="triage_agent",
    model=DEFAULT_MODEL,
    instruction="""You are the Triage Agent in Salon Payments Ops.
Your job is to inspect an exception by ID and classify its root cause.
Classification categories:
- missing_in_ledger: Stripe has a charge, but webhook was dropped or missed.
- missing_in_stripe: Internal ledger has payment, but Stripe never received or confirmed it.
- amount_mismatch: Stripe captured amount differs from internal ledger entry amount.
- duplicate_charge: Multiple Stripe charges exist for a single customer booking.
- failed_payout: Payout to salon bank account failed in Stripe.
Return the classified kind, delta amount, and key references.""",
    tools=[FunctionTool(get_exception_details)],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)

# ===================== 2. INVESTIGATOR AGENT =====================
investigator_agent = LlmAgent(
    name="investigator_agent",
    model=DEFAULT_MODEL,
    instruction="""You are the Investigator Agent in Salon Payments Ops.
Your job is to gather verifiable evidence for a given exception.
Use read-only tools to inspect:
1. Exception details
2. Internal double-entry ledger records
3. Stripe balance transaction status
4. Webhook and audit event timelines
Collect all relevant record IDs as evidence citations.""",
    tools=[
        FunctionTool(get_exception_details),
        FunctionTool(get_ledger_entry),
        FunctionTool(get_stripe_transaction),
        FunctionTool(get_event_history),
    ],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)

# ===================== 3. PROPOSER AGENT =====================
proposer_agent = LlmAgent(
    name="proposer_agent",
    model=DEFAULT_MODEL,
    instruction="""You are the Proposer Agent in Salon Payments Ops.
Your job is to produce a structured proposal to fix a verified reconciliation discrepancy.
Allowed actions:
- refund_customer: For duplicate charges or overcharges.
- post_ledger_adjustment: For missing ledger entries or rounding differences.
- retry_payout: For failed bank payouts.
- ignore_rounding: For minor variance <= 1 cent within tolerance.

Rules:
1. You can ONLY call the create_proposal tool. You CANNOT move money directly.
2. You MUST cite existing, verified record IDs in evidence_ids. Never invent IDs.
3. Keep amount_minor accurate in integer minor units (cents).
4. Provide a clear, factual justification in reason.""",
    tools=[FunctionTool(create_proposal)],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)

# ===================== 4. REPORTER AGENT =====================
reporter_agent = LlmAgent(
    name="reporter_agent",
    model=DEFAULT_MODEL,
    instruction="""You are the Reporter Agent in Salon Payments Ops.
Your job is to aggregate weekly operational metrics and produce a digest of exceptions,
breakdown by kind, proposal outcomes, and unresolved discrepancies.""",
    tools=[FunctionTool(generate_report)],
    before_model_callback=before_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)
