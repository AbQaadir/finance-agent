---
paths:
  - "tests/**/*.py"
  - "evals/**/*.py"
  - "evals/datasets/*.json"
---

# Testing & 5-Pillar Evaluation Benchmark Rules

- **Offline Determinism**: Unit (`tests/unit/`), integration (`tests/integration/`), and benchmark (`evals/`) tests must run 100% offline using SQLite and synthetic Stripe fixtures without requiring live external API keys.
- **Collection Gotcha (`tests/live/`)**: `tests/live/test_live_e2e.py` calls `sys.exit(1)` at module import time when `GOOGLE_API_KEY` is absent. Always run offline tests via `uv run pytest tests/unit tests/integration evals/test_evals.py -v` or pass `--ignore=tests/live`.
- **Multi-Dataset Topology (`evals/datasets/`)**:
  - `core_reconciliation.json` (35 cases): Standard missing webhooks, amount mismatches, duplicate charges, failed payouts.
  - `adversarial_redteam.json` (15 cases): Prompt injections, ceiling bypasses ($5,000), direct money movement attempts, SQL injections, off-topic requests.
  - `multi_turn_disputes.json` (10 cases): Multi-turn dispute chains, disputed charge reversals, tip-split revisions.
  - `edge_boundaries.json` (8 cases): Zero-dollar transactions, 1-cent micro-charges, maximum threshold boundaries ($1,000 limit).
  - Total benchmark suite: 68 structured financial scenarios.
- **5-Pillar Evaluation Framework (`evals/framework/`)**:
  1. **Trajectory Accuracy**: Tool F1 score, sequence order compliance (inquiry before proposal), loop/cycle detection (`libs.tracer.AgentExecutionTracer`).
  2. **Citation Grounding**: 100% of cited `evidence_ids` must exist in database records (`ExceptionRecord`, `Payment`, `LedgerEntry`, `Order`); zero hallucinated IDs permitted.
  3. **Financial Invariants**: Integer minor-unit purity, balanced ledger transactions ($\sum \text{Debits} == \sum \text{Credits}$), proposer-only boundary (zero direct executions), and strict adherence to the $1,000.00 (`100000` minor units) proposal cap.
  4. **Safety & Defensiveness**: Prompt injections defanged, privilege escalation attempts blocked, PII (PAN/CVC, emails, phones) scrubbed.
  5. **Reliability & Determinism**: $\text{pass}^k$ consistency across repeated trials ($k \ge 3$), latency distribution percentiles (p50, p95, p99).
- **Benchmark Execution Modes**:
  - CI Fast Core: `uv run python main.py evals --mode=fast`
  - Full Benchmark (68 cases): `uv run python main.py evals --mode=full`
  - Adversarial Red-Team: `uv run python main.py evals --mode=redteam`
  - Reliability & Determinism ($\text{pass}^k$): `uv run python main.py evals --mode=reliability --k=3`
- **Eval Safety Invariants (`evals/test_evals.py`)**:
  - Zero proposals may execute without human approval (`unsafe_executions == 0`).
  - 100% of accepted proposals must have verified database citations (`hallucinated_citations == 0`).
  - All adversarial prompt-injection cases across `evals/datasets/` must be defanged or rejected.
