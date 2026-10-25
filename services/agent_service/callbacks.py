"""
ADK Callbacks bridged to NVIDIA NeMo Guardrails:
1. Input Rails: PII Redaction & Prompt Injection Defanging before model calls
2. Action / Execution Rails: Default-deny policy check before tool calls
3. Output Rails: Audit logging, evidence grounding verification, and output sanitization after tool calls
"""

from typing import Dict, Any, Optional
from libs.policy import PolicyViolation
from libs.ledger.engine import get_db_session
from libs.ledger.operations import record_audit
from libs.guardrails import get_guardrails_service


def before_model_callback(context: Any, llm_request: Any) -> None:
    """
    NeMo Guardrails Input Rail:
    Executed immediately before transmitting any prompt or context to the LLM.
    Redacts PII and neutralizes injection triggers.
    """
    guardrails = get_guardrails_service()
    if hasattr(llm_request, "contents") and llm_request.contents:
        for content in llm_request.contents:
            if hasattr(content, "parts") and content.parts:
                for part in content.parts:
                    if hasattr(part, "text") and part.text:
                        part.text = guardrails.guard_input(part.text)


def before_tool_callback(tool: Any, args: Dict[str, Any], context: Any) -> Optional[Dict[str, Any]]:
    """
    NeMo Guardrails Action / Execution Rail:
    Default-deny security gate executed prior to every tool call.
    Enforces whitelist authorization, argument types, and maximum amount thresholds.
    """
    tool_name = getattr(tool, "name", str(tool))
    guardrails = get_guardrails_service()
    guardrails.guard_tool_call(tool_name, args)
    return None


def after_tool_callback(tool: Any, args: Dict[str, Any], context: Any, tool_output: Any) -> Optional[Dict[str, Any]]:
    """
    NeMo Guardrails Output Rail & Audit Trail:
    Audit logging hook executed immediately after each tool execution.
    Persists structured audit record with correlation ID into the ledger database.
    """
    tool_name = getattr(tool, "name", str(tool))
    correlation_id = getattr(context, "session_id", "session_untracked")
    guardrails = get_guardrails_service()

    with get_db_session() as session:
        record_audit(
            session=session,
            correlation_id=correlation_id,
            actor=f"guardrails:nemo:tool:{tool_name}",
            event="tool_execution",
            details={
                "tool": tool_name,
                "args": args,
                "output_summary": str(tool_output)[:500] if tool_output else None,
            },
        )

    # Sanitize and verify output
    if isinstance(tool_output, dict):
        if tool_name == "create_proposal" and tool_output.get("success"):
            # Output rail verification
            guardrails.guard_output(args)
        return guardrails.guard_output(tool_output) if tool_name == "create_proposal" else tool_output
    return None
