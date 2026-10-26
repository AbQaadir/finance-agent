---
name: eval
description: Run, analyze, and inspect the 5-pillar financial agent evaluation framework across 68 benchmark scenarios and 4 evaluation modes.
argument-hint: "[fast|full|redteam|reliability|report]"
---

# Agent Evaluation Framework Skill (`/eval`)

Manage and run the 5-pillar evaluation framework located in `evals/framework/`.

## Evaluation Modes

1. **Fast CI Mode (Default)**:
   Runs the core reconciliation dataset (35 cases) for rapid iteration:
   ```bash
   uv run python main.py evals --mode=fast
   ```

2. **Full Comprehensive Benchmark**:
   Runs all 68 test cases across all 4 datasets:
   ```bash
   uv run python main.py evals --mode=full
   ```

3. **Adversarial Red-Team Suite**:
   Runs the 15 adversarial security scenarios (prompt injections, ceiling bypasses, SQL injections, off-topic requests):
   ```bash
   uv run python main.py evals --mode=redteam
   ```

4. **Reliability & Consistency Mode**:
   Runs multi-trial pass^k verification to test agent determinism across runs:
   ```bash
   uv run python main.py evals --mode=reliability --k=3
   ```

5. **Pytest Invariant Suite**:
   Runs pytest assertions asserting zero safety violations and 100% citation grounding:
   ```bash
   uv run pytest evals/test_evals.py -v
   ```

## 5-Pillar Scorecard Metrics
- **Pillar 1: Trajectory Accuracy**: Tool call F1, sequence order validity, loop/cycle detection.
- **Pillar 2: Citation Grounding**: Verified DB citation rate, hallucinated citation rate (target: 0.0%).
- **Pillar 3: Financial Invariants**: Double-entry balance adherence, integer minor units, $1,000 threshold compliance, zero direct money-movement.
- **Pillar 4: Safety & Defensiveness**: Prompt injection defanging, privilege escalation defense, PII masking.
- **Pillar 5: Reliability & Latency**: $\text{pass}^k$ consistency across repeated trials, latency percentiles (p50, p95).

Reports are saved to `evals/reports/eval_report_latest.md` and timestamped JSON files in `evals/reports/`.
