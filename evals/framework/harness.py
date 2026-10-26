"""
Evaluation Harness for Salon Payments Ops Agent.
Coordinates multi-pillar evaluation runs across core cases, adversarial datasets,
multi-turn dispute workflows, and reliability trials.
"""

from dataclasses import dataclass, field
from pathlib import Path
import json
import time
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from libs.ledger.engine import _engine, init_db
from libs.ledger.models import Base, ExceptionRecord, Proposal, Order, Payment
from services.agent_service.coordinator import run_exception_investigation
from evals.framework.tracer import AgentExecutionTracer
from evals.framework.metrics.trajectory import evaluate_trajectory
from evals.framework.metrics.grounding import evaluate_citation_grounding
from evals.framework.metrics.financial import evaluate_financial_invariants
from evals.framework.metrics.safety import evaluate_safety_and_redteam
from evals.framework.metrics.reliability import calculate_pass_at_k, calculate_latency_percentiles
from evals.framework.reporter import EvaluationScorecard, CaseEvaluationRecord, EvaluationReporter

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"
LEGACY_GOLDEN_PATH = Path(__file__).resolve().parent.parent / "golden_dataset.json"


@dataclass
class EvaluationConfig:
    mode: str = "fast"  # 'fast', 'full', 'redteam', 'reliability'
    k_trials: int = 1
    datasets: List[str] = field(default_factory=list)
    output_dir: Optional[Path] = None


class EvaluationHarness:
    """
    Executes multi-pillar evaluation benchmark runs.
    """

    def __init__(self, config: Optional[EvaluationConfig] = None):
        self.config = config or EvaluationConfig()

    def load_dataset_cases(self) -> List[Dict[str, Any]]:
        """Loads cases based on active evaluation mode."""
        cases: List[Dict[str, Any]] = []

        if self.config.mode == "fast":
            # Uses core reconciliation cases
            core_path = DATASETS_DIR / "core_reconciliation.json"
            if core_path.exists():
                with open(core_path, "r", encoding="utf-8") as f:
                    cases = json.load(f)
            elif LEGACY_GOLDEN_PATH.exists():
                with open(LEGACY_GOLDEN_PATH, "r", encoding="utf-8") as f:
                    cases = json.load(f)

        elif self.config.mode == "redteam":
            rt_path = DATASETS_DIR / "adversarial_redteam.json"
            if rt_path.exists():
                with open(rt_path, "r", encoding="utf-8") as f:
                    cases = json.load(f)
            else:
                # Fallback to adversarial cases in legacy golden
                with open(LEGACY_GOLDEN_PATH, "r", encoding="utf-8") as f:
                    all_cases = json.load(f)
                    cases = [c for c in all_cases if "Adversarial" in c.get("name", "")]

        elif self.config.mode in ("full", "reliability"):
            # Load all available dataset files
            target_files = [
                DATASETS_DIR / "core_reconciliation.json",
                DATASETS_DIR / "adversarial_redteam.json",
                DATASETS_DIR / "multi_turn_disputes.json",
                DATASETS_DIR / "edge_boundaries.json",
            ]
            loaded = False
            for p in target_files:
                if p.exists():
                    with open(p, "r", encoding="utf-8") as f:
                        cases.extend(json.load(f))
                    loaded = True

            if not loaded and LEGACY_GOLDEN_PATH.exists():
                with open(LEGACY_GOLDEN_PATH, "r", encoding="utf-8") as f:
                    cases = json.load(f)

        return cases

    def run(self) -> EvaluationScorecard:
        """Executes the full evaluation run and compiles results into an EvaluationScorecard."""
        cases = self.load_dataset_cases()
        if not cases:
            raise ValueError(f"No test cases loaded for mode '{self.config.mode}'.")

        # Database initialization
        Base.metadata.drop_all(_engine)
        init_db(_engine)

        k_runs = self.config.k_trials if self.config.mode == "reliability" else 1
        case_success_matrix: List[List[bool]] = [[] for _ in range(len(cases))]
        all_latencies_ms: List[float] = []

        last_run_records: List[CaseEvaluationRecord] = []

        for trial in range(k_runs):
            Base.metadata.drop_all(_engine)
            init_db(_engine)
            for idx, case in enumerate(cases):
                case_id = case["id"]
                kind = case["kind"]
                expected_action = case["expected_action"]
                delta_minor = case["delta_minor"]
                stripe_ref = case.get("stripe_ref")
                ledger_ref = case.get("ledger_ref")

                # Seed fresh database state for this case
                exc_id = f"exc_{case_id}_{trial}"
                with Session(_engine) as session:
                    exc = ExceptionRecord(
                        id=exc_id,
                        kind=kind,
                        ledger_ref=ledger_ref,
                        stripe_ref=stripe_ref,
                        delta_minor=delta_minor,
                        status="open",
                    )
                    session.add(exc)

                    if ledger_ref:
                        session.add(
                            Order(
                                id=ledger_ref,
                                salon_id="salon_eval",
                                type="deposit",
                                amount_minor=delta_minor,
                                status="paid",
                            )
                        )
                    if stripe_ref:
                        session.add(
                            Payment(
                                id=f"pmt_{case_id}_{trial}",
                                order_id=ledger_ref or f"ord_{case_id}_{trial}",
                                stripe_payment_intent_id=stripe_ref,
                                status="succeeded",
                                idempotency_key=f"idem_{case_id}_{trial}",
                                amount_minor=delta_minor,
                            )
                        )
                    session.commit()

                # Execute investigation under tracer
                with AgentExecutionTracer(case_id=case_id) as trajectory:
                    t0 = time.perf_counter()
                    inv_res = run_exception_investigation(exc_id)
                    duration_ms = (time.perf_counter() - t0) * 1000.0

                all_latencies_ms.append(duration_ms)

                classification = inv_res.get("classification")
                proposal_info = inv_res.get("proposal", {})
                actual_action = proposal_info.get("action", "none")
                evidence_ids = proposal_info.get("evidence_ids", [])
                proposal_reason = proposal_info.get("reason", "")

                with Session(_engine) as session:
                    prop_rec = session.scalar(select(Proposal).where(Proposal.exception_id == exc_id))
                    if prop_rec:
                        if not evidence_ids and prop_rec.evidence_ids:
                            evidence_ids = prop_rec.evidence_ids
                        if not proposal_reason and prop_rec.reason:
                            proposal_reason = prop_rec.reason
                        proposal_info["evidence_ids"] = evidence_ids
                        proposal_info["reason"] = proposal_reason
                        proposal_info["amount_minor"] = prop_rec.amount_minor
                        proposal_info["action"] = prop_rec.action

                    # 1. Classification & Action Accuracy
                    class_ok = (classification == kind)
                    action_ok = (actual_action == expected_action)

                    # 2. Grounding Evaluation
                    grounding_stats = evaluate_citation_grounding(
                        evidence_ids=evidence_ids,
                        session=session,
                        exception_id=exc_id,
                    )

                    # 3. Financial Invariant Evaluation
                    financial_stats = evaluate_financial_invariants(
                        session=session,
                        proposal_dict=proposal_info,
                        exception_id=exc_id,
                    )

                # 4. Safety & Red-Teaming Evaluation
                safety_stats = evaluate_safety_and_redteam(
                    case=case,
                    proposed_action=actual_action,
                    proposal_reason=proposal_reason,
                    trajectory_logs=[step.tool_name for step in trajectory.steps],
                )

                # Overall case pass criteria
                case_passed = (
                    class_ok
                    and action_ok
                    and grounding_stats["is_grounded"]
                    and financial_stats["passed"]
                    and safety_stats["passed"]
                )

                case_success_matrix[idx].append(case_passed)

                if trial == 0:
                    last_run_records.append(
                        CaseEvaluationRecord(
                            case_id=case_id,
                            name=case.get("name", case_id),
                            kind=kind,
                            expected_action=expected_action,
                            actual_action=actual_action,
                            classification_correct=class_ok,
                            action_match=action_ok,
                            citation_grounded=grounding_stats["is_grounded"],
                            financial_valid=financial_stats["passed"],
                            safety_passed=safety_stats["passed"],
                            duration_ms=round(duration_ms, 2),
                        )
                    )

        # Aggregate Scorecard
        total_cases = len(cases)
        passed_cases = sum(1 for runs in case_success_matrix if runs[0])
        class_correct = sum(1 for c in last_run_records if c.classification_correct)
        action_correct = sum(1 for c in last_run_records if c.action_match)
        grounded_count = sum(1 for c in last_run_records if c.citation_grounded)
        financial_valid_count = sum(1 for c in last_run_records if c.financial_valid)
        safety_passed_count = sum(1 for c in last_run_records if c.safety_passed)

        latency_stats = calculate_latency_percentiles(all_latencies_ms)
        pass_k_score = calculate_pass_at_k(case_success_matrix)

        scorecard = EvaluationScorecard(
            mode=self.config.mode,
            total_cases=total_cases,
            passed_cases=passed_cases,
            classification_accuracy=round((class_correct / total_cases) * 100.0, 2),
            action_accuracy=round((action_correct / total_cases) * 100.0, 2),
            grounding_rate=round((grounded_count / total_cases) * 100.0, 2),
            financial_compliance_rate=round((financial_valid_count / total_cases) * 100.0, 2),
            safety_pass_rate=round((safety_passed_count / total_cases) * 100.0, 2),
            pass_at_k=pass_k_score,
            k_trials=k_runs,
            hallucinated_citations_count=sum(1 for c in last_run_records if not c.citation_grounded),
            unsafe_executions_count=sum(1 for c in last_run_records if not c.financial_valid),
            injections_compromised_count=sum(1 for c in last_run_records if not c.safety_passed),
            latency_p50_ms=latency_stats["p50_ms"],
            latency_p90_ms=latency_stats["p90_ms"],
            latency_p99_ms=latency_stats["p99_ms"],
            cases=last_run_records,
        )

        return scorecard
