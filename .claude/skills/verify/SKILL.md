---
name: verify
description: Run the complete Salon Payments Ops verification suite (unit tests including NeMo Guardrails, integration tests, and 35-case golden evaluation benchmark). Use after making code changes or when asked to verify the repository.
---

# Repository Verification Loop (`/verify`)

Execute the full verification pipeline in order and report exact pass/fail evidence:

1. **Unit & Integration Test Suite (including NVIDIA NeMo Guardrails)**:
   ```bash
   uv run pytest tests/unit tests/integration -v
   ```
2. **35-Case Golden Evaluation Benchmark**:
   ```bash
   uv run python -m evals.runner
   ```
3. **Zero Unsafe Execution & 100% Citation Grounding Assertions**:
   ```bash
   uv run pytest evals/test_evals.py -v
   ```

## Reporting Format
- State the pass/fail count for `tests/` (expected: 40 passed) and `evals/test_evals.py` (expected: 1 passed).
- Report the classification accuracy, proposal action accuracy, citation grounding rate, and unsafe execution count from `evals.runner`.
- If any check fails, diagnose the root cause before proposing a fix.
