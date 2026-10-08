"""
Security policy engine implementing default-deny guardrails for ADK agent tool calls.
"""

from typing import Dict, Any, Set, List

ALLOWED_TOOLS: Set[str] = {
    "get_ledger_entry",
    "get_stripe_transaction",
    "get_event_history",
    "get_exception_details",
    "create_proposal",
    "generate_report",
}

ALLOWED_PROPOSAL_ACTIONS: Set[str] = {
    "refund_customer",
    "post_ledger_adjustment",
    "retry_payout",
    "ignore_rounding",
}

MAX_PROPOSAL_AMOUNT_MINOR: int = 100000  # $1,000.00 limit for automated exception proposals


class PolicyViolation(Exception):
    """Raised when an agent tool call violates safety or authorization policies."""
    pass


def validate_tool_call(tool_name: str, args: Dict[str, Any]) -> None:
    """
    Validates a tool invocation against strict security policies.
    Raises PolicyViolation if disallowed or arguments exceed boundaries.
    """
    if tool_name not in ALLOWED_TOOLS:
        raise PolicyViolation(
            f"Security policy denial: Tool '{tool_name}' is not in the allowed tool whitelist."
        )

    if tool_name == "create_proposal":
        action = args.get("action")
        amount_minor = args.get("amount_minor", 0)
        reason = args.get("reason", "")
        evidence_ids = args.get("evidence_ids", [])
        confidence = args.get("confidence", 1.0)

        if action not in ALLOWED_PROPOSAL_ACTIONS:
            raise PolicyViolation(
                f"Invalid proposal action '{action}'. Permitted actions: {sorted(ALLOWED_PROPOSAL_ACTIONS)}"
            )

        if not isinstance(amount_minor, int) or amount_minor < 0:
            raise PolicyViolation("Proposal amount_minor must be a non-negative integer.")

        if amount_minor > MAX_PROPOSAL_AMOUNT_MINOR:
            raise PolicyViolation(
                f"Proposal amount {amount_minor} exceeds maximum safety ceiling of {MAX_PROPOSAL_AMOUNT_MINOR} minor units."
            )

        if not isinstance(reason, str) or len(reason.strip()) < 5:
            raise PolicyViolation("Proposal must contain an informative explanation reason.")

        if not isinstance(evidence_ids, list):
            raise PolicyViolation("Proposal evidence_ids must be a list of cited record IDs.")

        if not (0.0 <= confidence <= 1.0):
            raise PolicyViolation(f"Confidence score {confidence} must be between 0.0 and 1.0.")

    elif tool_name in {"get_ledger_entry", "get_stripe_transaction", "get_exception_details"}:
        # Ensure identifier arguments are valid strings without malicious control chars
        for key, val in args.items():
            if not isinstance(val, str) or len(val) > 128:
                raise PolicyViolation(f"Invalid lookup key '{key}' in query tool '{tool_name}'.")
            if any(char in val for char in [";", "\n", "\r", "\0"]):
                raise PolicyViolation(f"Illegal characters detected in query argument '{key}'.")
