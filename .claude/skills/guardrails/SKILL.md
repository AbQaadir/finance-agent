---
name: guardrails
description: Inspect and verify NVIDIA NeMo Guardrails configuration, Colang dialog flows, and 5-layer rails pipeline (input, dialog, context, action, output) in the Salon Payments Ops platform.
argument-hint: "[test|status|inspect]"
---

# NVIDIA NeMo Guardrails Skill

Manage and verify the 5-layer NeMo Guardrails security pipeline in `libs/guardrails/`.

## Rails Architecture Overview
1. **Input Rails**: Intercept user messages and customer notes to scrub PII and neutralize prompt injections.
2. **Dialog Rails (Colang)**: Enforce conversational state and block off-topic requests or unauthorized money movements in `libs/guardrails/config/rails.co`.
3. **Retrieval Rails**: Defend against adversarial data poisoning in transaction context.
4. **Action / Execution Rails**: Intercept tool calls to enforce `ALLOWED_TOOLS` and `$1,000.00` amount ceiling.
5. **Output Rails**: Assert citation grounding against database records and prevent PII leakage in proposals.

## Commands
- Run NeMo Guardrails unit tests:
  ```bash
  uv run pytest tests/unit/test_nemo_guardrails.py -v
  ```
- Run full verification suite:
  ```bash
  uv run pytest tests/unit tests/integration evals/test_evals.py -v
  ```
