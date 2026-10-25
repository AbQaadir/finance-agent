"""
NVIDIA NeMo Guardrails Integration for Salon Payments Ops Agent.
Provides 5-layer rails architecture: Input, Dialog (Colang), Context, Action/Execution, Output.
"""

from .service import get_guardrails_service, NeMoGuardrailsService
from .actions import (
    check_pii_action,
    check_prompt_injection_action,
    validate_tool_call_action,
    verify_citation_grounding_action,
)

__all__ = [
    "get_guardrails_service",
    "NeMoGuardrailsService",
    "check_pii_action",
    "check_prompt_injection_action",
    "validate_tool_call_action",
    "verify_citation_grounding_action",
]
