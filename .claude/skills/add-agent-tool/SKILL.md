---
name: add-agent-tool
description: Step-by-step workflow for adding a new read-only ADK tool to the agent service while maintaining default-deny policy, PII redaction, and unit test coverage.
argument-hint: "[tool_name]"
disable-model-invocation: true
---

# Add a New ADK Agent Tool (`$ARGUMENTS`)

Follow every step in order to preserve the default-deny security posture:

1. **Verify Read-Only Boundary**:
   - Confirm the tool does NOT move money, call Stripe write APIs, or mutate `ledger_entries`. The agent service is strictly a proposer.
2. **Implement Tool Function (`services/agent_service/tools.py`)**:
   - Write the function with explicit type annotations and a descriptive docstring (used by Google ADK as the tool schema).
   - Scrub any dictionary or text outputs containing customer metadata using `scrub_dict_pii` or `scrub_pii` from `libs/redaction/sanitizer.py`.
3. **Update Default-Deny Whitelist (`libs/policy/rules.py`)**:
   - Add the tool name to `ALLOWED_TOOLS`.
   - Add argument validation in `validate_tool_call()` (reject control characters `;`, `\n`, `\r`, `\0` and enforce length limits).
4. **Register on Subagent (`services/agent_service/subagents.py`)**:
   - Attach the tool only to the minimum required subagent (e.g., `investigator_agent` or `reporter_agent`).
5. **Verify (`tests/unit/test_agent_service.py`)**:
   - Add unit tests covering both valid tool calls and `PolicyViolation` rejection on malformed inputs.
   - Run `uv run pytest tests/unit/test_agent_service.py -v`.
