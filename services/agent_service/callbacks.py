"""
ADK Callbacks implementing enterprise guardrails:
1. PII Redaction before model calls
2. Default-deny policy check before tool calls
3. Audit logging and output sanitization after tool calls
"""

from typing import Dict, Any, Optional
from libs.policy import validate_tool_call, PolicyViolation
from libs.redaction import redact_pii, scrub_dict_pii
from libs.ledger.engine import get_db_session
from libs.ledger.operations import record_audit


def before_model_callback(context: Any, llm_request: Any) -> None:
    """
    Hook executed immediately before transmitting any prompt or context to the LLM.
    Redacts personal identity information (PII).
    """
    # Scrub text contents in the request
    if hasattr(llm_request, "contents") and llm_request.contents:
        for content in llm_request.contents:
            if hasattr(content, "parts") and content.parts:
                for part in content.parts:
                    if hasattr(part, "text") and part.text:
                        part.text = redact_pii(part.text)


def before_tool_callback(tool: Any, args: Dict[str, Any], context: Any) -> Optional[Dict[str, Any]]:
    """
    Default-deny security gate executed prior to every tool call.
    Enforces whitelist authorization, argument types, and maximum amount thresholds.
    """
    tool_name = getattr(tool, "name", str(tool))
    # Validate via policy library
    validate_tool_call(tool_name, args)
    return None


def after_tool_callback(tool: Any, args: Dict[str, Any], context: Any, tool_output: Any) -> Optional[Dict[str, Any]]:
    """
    Audit logging hook executed immediately after each tool execution.
    Persists structured audit record with correlation ID into the ledger database.
    """
    tool_name = getattr(tool, "name", str(tool))
    correlation_id = getattr(context, "session_id", "session_untracked")

    with get_db_session() as session:
        record_audit(
            session=session,
            correlation_id=correlation_id,
            actor=f"agent:tool:{tool_name}",
            event="tool_execution",
            details={
                "tool": tool_name,
                "args": scrub_dict_pii(args),
                "output_summary": str(tool_output)[:500] if tool_output else None,
            },
        )

    # Sanitize output if dictionary
    if isinstance(tool_output, dict):
        return scrub_dict_pii(tool_output)
    return None
