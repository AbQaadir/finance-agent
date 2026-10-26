---
name: verify
description: Run the complete Salon Payments Ops verification suite (unit tests including NeMo Guardrails, integration tests, and multi-pillar evaluation benchmark). Use after making code changes or when asked to verify the repository.
---

# Repository Verification Loop (`/verify`)

Execute the full verification pipeline in order and report exact pass/fail evidence:

1. **Unit & Integration Test Suite (including NVIDIA NeMo Guardrails)**:
   ```bash
   uv run pytest tests/unit tests/integration -v
   ```
2. **Multi-Pillar Evaluation Benchmark**:
   ```bash
   uv run python main.py evals --mode=fast        # Fast CI core
   uv run python main.py evals --mode=full        # Full 68-case benchmark
   uv run python main.py evals --mode=redteam     # Adversarial red-team
   uv run python main.py evals --mode=reliability --k=3 # Multi-trial pass^k
   ```
3. **Safety, Invariant & Citation Grounding Assertions**:
   ```bash
   uv run pytest evals/test_evals.py -v
   ```

## Reporting Format
- State the pass/fail count for `tests/` (expected: 40 passed) and `evals/test_evals.py` (expected: 2 passed).
- Report the classification accuracy, proposal action accuracy, citation grounding rate, and unsafe execution count from `evals.runner`.
- If any check fails, diagnose the root cause before proposing a fix.
