"""
PII Redaction and free-text prompt sanitization engine.
Protects sensitive personal data and mitigates prompt-injection attacks.
"""

import re
from typing import Dict, Any

# Regex patterns for common sensitive PII
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PHONE_REGEX = re.compile(r"\b(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")

# Prompt injection signatures to neutralize in free-text fields
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"human\s*:\s*", re.IGNORECASE),
    re.compile(r"assistant\s*:\s*", re.IGNORECASE),
    re.compile(r"you\s+must\s+(now\s+)?refund", re.IGNORECASE),
    re.compile(r"bypass\s+approval", re.IGNORECASE),
    re.compile(r"\[system_prompt\]", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
]


def redact_pii(text: str) -> str:
    """
    Scrubs identifiable emails, phone numbers, card numbers, and SSNs from text.
    """
    if not text:
        return ""
    
    redacted = EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
    redacted = CARD_REGEX.sub("[REDACTED_CARD]", redacted)
    redacted = SSN_REGEX.sub("[REDACTED_SSN]", redacted)
    redacted = PHONE_REGEX.sub("[REDACTED_PHONE]", redacted)
    return redacted



def sanitize_free_text(text: str) -> str:
    """
    Sanitizes untrusted user-submitted text (e.g. booking notes, client messages)
    by redacting PII, defanging injection prompts, and quoting it safely.
    """
    if not text:
        return ""

    cleaned = redact_pii(text)

    # Defang injection triggers
    for pattern in INJECTION_PATTERNS:
        cleaned = pattern.sub("[DEFANGED_COMMAND]", cleaned)

    # Strip dangerous control characters and null bytes
    cleaned = cleaned.replace("\0", "").replace("\r", " ")
    
    # Wrap in explicit data boundaries so LLM treats as literal data
    return f"'''{cleaned.strip()}'''"


def scrub_dict_pii(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively redacts PII strings within a dictionary structure.
    """
    cleaned: Dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str):
            cleaned[k] = redact_pii(v)
        elif isinstance(v, dict):
            cleaned[k] = scrub_dict_pii(v)
        elif isinstance(v, list):
            cleaned[k] = [
                redact_pii(item) if isinstance(item, str)
                else (scrub_dict_pii(item) if isinstance(item, dict) else item)
                for item in v
            ]
        else:
            cleaned[k] = v
    return cleaned
