"""
Agent Execution Tracer for Salon Payments Ops.
Captures structured multi-step trajectories, tool invocations, parameter payloads,
execution latencies, and state transitions during evaluation turns.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Dict, Any, List, Optional
from contextvars import ContextVar
from contextlib import contextmanager

# Context variable tracking active execution trajectory
_current_trajectory: ContextVar[Optional["AgentTrajectory"]] = ContextVar(
    "_current_trajectory", default=None
)


@dataclass
class ToolExecutionStep:
    tool_name: str
    args: Dict[str, Any]
    output: Any
    duration_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AgentTrajectory:
    case_id: str
    steps: List[ToolExecutionStep] = field(default_factory=list)
    agent_handoffs: List[str] = field(default_factory=list)
    final_output: Dict[str, Any] = field(default_factory=dict)
    total_duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def tool_names(self) -> List[str]:
        return [step.tool_name for step in self.steps]

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def record_step(self, tool_name: str, args: Dict[str, Any], output: Any, duration_ms: float) -> None:
        self.steps.append(
            ToolExecutionStep(
                tool_name=tool_name,
                args=args,
                output=output,
                duration_ms=duration_ms,
            )
        )

    def record_handoff(self, agent_name: str) -> None:
        self.agent_handoffs.append(agent_name)


class AgentExecutionTracer:
    """
    Context manager to trace and capture the execution trajectory of an agent.
    """

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.trajectory = AgentTrajectory(case_id=case_id)
        self._token = None
        self._start_time = 0.0

    def __enter__(self) -> AgentTrajectory:
        self._start_time = time.perf_counter()
        self._token = _current_trajectory.set(self.trajectory)
        return self.trajectory

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.perf_counter() - self._start_time) * 1000.0
        self.trajectory.total_duration_ms = duration
        if exc_val:
            self.trajectory.error = str(exc_val)
        if self._token:
            _current_trajectory.reset(self._token)
        return False  # Do not suppress exceptions


def record_tracer_step(tool_name: str, args: Dict[str, Any], output: Any, duration_ms: float) -> None:
    """Helper invoked by tool hooks to record step into active trajectory."""
    traj = _current_trajectory.get()
    if traj is not None:
        traj.record_step(tool_name=tool_name, args=args, output=output, duration_ms=duration_ms)


def get_current_trajectory() -> Optional[AgentTrajectory]:
    """Returns the currently active trajectory if within a tracer context."""
    return _current_trajectory.get()
