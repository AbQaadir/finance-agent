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
- State the total pass/fail count across the full test suite (expected: 42 passed — 40 unit/integration tests and 2 eval assertion tests).
- Report the 5-pillar evaluation scorecard from `evals/reports/eval_report_latest.md`:
  1. **Trajectory Accuracy**: Tool F1 score, sequence order compliance, loop-free execution.
  2. **Citation Grounding**: 100% database citation rate, 0% hallucination rate.
  3. **Financial Invariants**: Balance invariant adherence, minor-unit purity, $1,000 ceiling compliance, 0 direct executions.
  4. **Safety & Defensiveness**: Prompt injection neutralization rate, privilege escalation defense rate, PII redaction.
  5. **Reliability & Latency**: $\text{pass}^k$ consistency ($k=3$), median and tail latency (p50, p95).
- If any check fails, diagnose the root cause before proposing a fix.
