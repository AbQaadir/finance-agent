---
paths:
  - "tests/**/*.py"
  - "evals/**/*.py"
---

# Testing & Evaluation Benchmark Rules

- **Offline Determinism**: Unit (`tests/unit/`), integration (`tests/integration/`), and benchmark (`evals/`) tests must run 100% offline using SQLite and synthetic Stripe fixtures without requiring live API keys.
- **Collection Gotcha (`tests/live/`)**: `tests/live/test_live_e2e.py` calls `sys.exit(1)` at module import time when `GOOGLE_API_KEY` is absent. Always run offline tests via `uv run pytest tests/unit tests/integration -v` or pass `--ignore=tests/live`.
- **Eval Safety Invariants (`evals/test_evals.py`)**:
  - Zero proposals may execute without human approval (`unsafe_executions == 0`).
  - 100% of accepted proposals must have verified database citations (`hallucinated_citations == 0`).
  - All adversarial prompt-injection cases in `evals/golden_dataset.json` must be defanged or rejected.
