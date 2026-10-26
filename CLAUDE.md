# Salon Payments Ops Agent (`finance-agent`)

Enterprise financial operations platform pairing a deterministic double-entry accounting ledger with a Google ADK multi-agent exception investigation system on Cloud Run.

## Build, Run & Verification Commands (`uv`)
- **Run offline unit & integration tests**: `uv run pytest tests/unit tests/integration evals/test_evals.py -v` (42 offline tests; `tests/live/test_live_e2e.py` requires live `GOOGLE_API_KEY` in `.env`)
- **Run a single test file (preferred during iteration)**: `uv run pytest tests/unit/test_libs.py -v`
- **Run a single test function**: `uv run pytest tests/unit/test_libs.py -k "test_name" -v`
- **Run multi-pillar evaluation benchmark**: `uv run python main.py evals --mode=fast` (CI core) | Full benchmark: `uv run python main.py evals --mode=full` | Red-team: `uv run python main.py evals --mode=redteam` | Reliability: `uv run python main.py evals --mode=reliability --k=3`
- **Run safety, invariant & citation grounding eval assertions**: `uv run pytest evals/test_evals.py -v`
- **Run live Gemini/ADK E2E test (requires `GOOGLE_API_KEY` in `.env`)**: `uv run python main.py live-test`
- **Start Payments & Webhook API (port 8000)**: `uv run python main.py payments-api`
- **Start Human Approval Gate Service (port 8001)**: `uv run python main.py approval-service`
- **Run Daily Reconciliation Job**: `uv run python main.py recon-job`
- **Database migrations (Alembic)**: `uv run alembic upgrade head` | New revision: `uv run alembic revision --autogenerate -m "<description>"`

## Non-Negotiable Architecture & Financial Invariants
1. **Minor Integer Units Only**: IMPORTANT: Every monetary value (`amount_minor`, `debit_minor`, `credit_minor`, `delta_minor`) MUST be an integer representing minor currency units (cents). Never use `float` or `Decimal` for storage or arithmetic.
2. **Double-Entry Balance Invariant**: Every transaction posted in `libs/ledger/` must satisfy `sum(debit_minor) == sum(credit_minor)` with non-negative legs. Ledger entries (`ledger_entries` table) are strictly append-only; never update or delete posted rows—post a balancing reversal entry instead.
3. **Hamilton-Hare Tip Splitting**: Multi-staff tip splits in `libs/tipsplit/calculator.py` must use basis points summing to `10000` (100.00%) and allocate remainders via the Hamilton-Hare largest-remainder method so `sum(allocated) == total_tip_minor`.
4. **Proposer-Only Agent Boundary**: IMPORTANT: `services/agent_service/` has ZERO money-movement capabilities. Agents may only invoke read-only query tools and `create_proposal` (writing solely to the `proposals` table). Financial execution happens exclusively in `services/approval_service/executor.py` after human approval.
5. **Evidence Citation Grounding**: Every agent proposal must pass non-empty `evidence_ids` that resolve to real database records (`ExceptionRecord`, `Payment`, `LedgerEntry`, or `Order`).
6. **NVIDIA NeMo Guardrails & Policy Enforcement**: Every tool must be whitelisted in `libs/policy/rules.py` (`ALLOWED_TOOLS`) and enforced via `libs/guardrails/` action rails. Input rails sanitize free-text and redact PII. Dialog rails (Colang) block off-topic queries and direct payment attempts. Output rails assert 100% database evidence citation grounding.
7. **PCI DSS SAQ A Scope**: Never accept, log, or persist raw card numbers (PAN/CVC). Only handle opaque Stripe tokens and `PaymentIntent` IDs (`pi_*`).

## Workflow & Verification Rules
- Always close the verification loop before finishing a task: run the relevant `uv run pytest` test file(s) and `uv run pytest evals/test_evals.py -v` and show the output.
- Never edit existing migration files in `migrations/versions/` directly; create a new Alembic migration.
- When compacting context (`/compact`), always preserve the full list of modified files, any active exception/proposal IDs, and the exact test commands run.

## Architecture & Operations Reference Docs
- System topology & subsystem boundaries: `docs/architecture.md`
- Daily reconciliation & approval gate runbook: `docs/runbook.md`
- STRIDE threat model & prompt-injection defenses: `docs/threat_model.md`
