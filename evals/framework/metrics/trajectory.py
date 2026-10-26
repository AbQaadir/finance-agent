"""
Trajectory and Tool Governance Metrics.
Evaluates tool selection precision, recall, F1, loop detection, and sequence ordering.
"""

from typing import List, Dict, Any, Tuple, Optional
from evals.framework.tracer import AgentTrajectory, ToolExecutionStep


def calculate_tool_selection_f1(
    actual_tools: List[str],
    expected_tools: List[str],
) -> Dict[str, float]:
    """
    Computes precision, recall, and F1 score for tool selection.
    """
    if not expected_tools and not actual_tools:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not actual_tools:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    if not expected_tools:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}

    actual_set = set(actual_tools)
    expected_set = set(expected_tools)

    true_positives = len(actual_set.intersection(expected_set))
    precision = true_positives / len(actual_set) if actual_set else 0.0
    recall = true_positives / len(expected_set) if expected_set else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def detect_execution_loops(steps: List[ToolExecutionStep]) -> int:
    """
    Detects redundant execution loops where an agent calls the exact same tool
    with identical arguments consecutively.
    """
    if len(steps) < 2:
        return 0

    loop_count = 0
    for i in range(1, len(steps)):
        prev = steps[i - 1]
        curr = steps[i]
        if prev.tool_name == curr.tool_name and str(prev.args) == str(curr.args):
            loop_count += 1

    return loop_count


def evaluate_sequence_order(actual_sequence: List[str], expected_order: List[str]) -> float:
    """
    Evaluates whether tools were called in the expected logical sequence.
    Returns a score between 0.0 (completely reversed/disordered) and 1.0 (perfect order).
    """
    if not expected_order:
        return 1.0
    if not actual_sequence:
        return 0.0

    # Filter actual sequence to only tools present in expected_order
    filtered_actual = [t for t in actual_sequence if t in expected_order]
    if not filtered_actual:
        return 0.0

    # Check pairwise relative order
    correct_pairs = 0
    total_pairs = 0
    for i in range(len(expected_order)):
        for j in range(i + 1, len(expected_order)):
            t1 = expected_order[i]
            t2 = expected_order[j]
            if t1 in filtered_actual and t2 in filtered_actual:
                total_pairs += 1
                if filtered_actual.index(t1) <= filtered_actual.index(t2):
                    correct_pairs += 1

    return round(correct_pairs / total_pairs, 4) if total_pairs > 0 else 1.0


def evaluate_trajectory(
    trajectory: AgentTrajectory,
    expected_tools: Optional[List[str]] = None,
    expected_order: Optional[List[str]] = None,
    max_steps_allowed: int = 10,
) -> Dict[str, Any]:
    """
    Comprehensive evaluation of an agent trajectory.
    """
    actual_tools = trajectory.tool_names
    f1_stats = calculate_tool_selection_f1(actual_tools, expected_tools or [])
    loops = detect_execution_loops(trajectory.steps)
    order_score = evaluate_sequence_order(actual_tools, expected_order or [])
    step_limit_exceeded = len(trajectory.steps) > max_steps_allowed

    return {
        "step_count": len(trajectory.steps),
        "tool_precision": f1_stats["precision"],
        "tool_recall": f1_stats["recall"],
        "tool_f1": f1_stats["f1"],
        "loops_detected": loops,
        "order_score": order_score,
        "step_limit_exceeded": step_limit_exceeded,
        "passed": (f1_stats["f1"] >= 0.8 and loops == 0 and not step_limit_exceeded),
    }
