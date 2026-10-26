"""
Reliability and Telemetry Metrics.
Computes pass^k consistency across multiple stochastic iterations and latency distributions (p50, p90, p99).
"""

from typing import List, Dict, Any
import numpy as np


def calculate_pass_at_k(case_success_matrix: List[List[bool]]) -> float:
    """
    Computes pass^k reliability:
    Proportion of test cases that succeeded across ALL k trials.
    `case_success_matrix` is shape (num_cases, k).
    """
    if not case_success_matrix:
        return 0.0

    unanimous_passes = 0
    total_cases = len(case_success_matrix)

    for case_runs in case_success_matrix:
        if all(case_runs):
            unanimous_passes += 1

    return round((unanimous_passes / total_cases) * 100.0, 2)


def calculate_latency_percentiles(latencies_ms: List[float]) -> Dict[str, float]:
    """
    Calculates p50, p90, p99, mean, and max latency in milliseconds.
    """
    if not latencies_ms:
        return {
            "p50_ms": 0.0,
            "p90_ms": 0.0,
            "p99_ms": 0.0,
            "mean_ms": 0.0,
            "max_ms": 0.0,
        }

    arr = np.array(latencies_ms)
    return {
        "p50_ms": round(float(np.percentile(arr, 50)), 2),
        "p90_ms": round(float(np.percentile(arr, 90)), 2),
        "p99_ms": round(float(np.percentile(arr, 99)), 2),
        "mean_ms": round(float(np.mean(arr)), 2),
        "max_ms": round(float(np.max(arr)), 2),
    }
