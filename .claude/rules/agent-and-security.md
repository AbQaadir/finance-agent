---
paths:
  - "services/agent_service/**/*.py"
  - "libs/policy/**/*.py"
  - "libs/redaction/**/*.py"
  - "evals/**/*"
---

# Google ADK Agent & Security Guardrail Rules

- **Agent Hierarchy**: `coordinator_agent` orchestrates `triage_agent`, `investigator_agent`, `proposer_agent`, and `reporter_agent` (`services/agent_service/subagents.py`).
- **Strict Tool Separation**:
  - Inquiry tools (`get_exception_details`, `get_ledger_entry`, `get_stripe_transaction`, `get_event_history`, `generate_report`) MUST remain strictly read-only.
  - `create_proposal` is the ONLY write tool permitted for agents and may only insert `pending` rows into `proposals` and mark the `ExceptionRecord.status = "proposed"`.
- **Policy Enforcement (`libs/policy/rules.py`)**:
  - `MAX_PROPOSAL_AMOUNT_MINOR` is capped at `100000` ($1,000.00).
  - Permitted proposal actions: `refund_customer`, `post_ledger_adjustment`, `retry_payout`, `ignore_rounding`.
  - Query string arguments must reject control/injection characters (`;`, `\n`, `\r`, `\0`) and lengths > 128.
- **Prompt Injection & PII Defense (`libs/redaction/sanitizer.py`)**:
  - Always scrub emails, phone numbers, and PAN-like sequences via `scrub_pii` / `scrub_dict_pii` in `before_model_callback` and tool outputs.
  - Wrap untrusted booking notes with `sanitize_free_text` to neutralize `[DEFANGED_COMMAND]` patterns.
