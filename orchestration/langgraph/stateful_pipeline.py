#!/usr/bin/env python3
"""LangGraph stateful pipeline for complex R&D workflows.

Implements circuit breaker pattern with 3-strike rule and state persistence.
"""

import json
import sqlite3
from typing import TypedDict, Annotated, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import operator


class PipelineState(TypedDict):
    """Shared state across pipeline nodes."""
    task_id: str
    current_stage: str
    data: Dict[str, Any]
    errors: Annotated[List[Dict], operator.add]
    retry_count: Annotated[Dict[str, int], operator.or_]
    completed_stages: Annotated[List[str], operator.add]
    artifacts: Annotated[List[str], operator.add]


@dataclass
class StageResult:
    success: bool
    output: Any = None
    error: str = None
    next_stage: str = None


class CircuitBreaker:
    """3-strike circuit breaker for fault tolerance."""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.failure_counts: Dict[str, int] = {}
        self.circuit_open: Dict[str, bool] = {}

    def call(self, func, stage_name: str, *args, **kwargs) -> StageResult:
        """Execute function with circuit breaker protection."""
        if self.circuit_open.get(stage_name, False):
            return StageResult(
                success=False,
                error=f"Circuit open for {stage_name}: max retries exceeded"
            )

        try:
            result = func(*args, **kwargs)
            self.failure_counts[stage_name] = 0
            return StageResult(success=True, output=result)
        except Exception as e:
            self.failure_counts[stage_name] = self.failure_counts.get(stage_name, 0) + 1

            if self.failure_counts[stage_name] >= self.max_retries:
                self.circuit_open[stage_name] = True

            return StageResult(
                success=False,
                error=str(e),
                next_stage="error_handler" if self.circuit_open[stage_name] else stage_name
            )


class StatefulPipeline:
    """LangGraph-inspired stateful execution pipeline with ordered stages."""

    def __init__(self, db_path: str = "pipeline_state.db"):
        self.db_path = db_path
        self.circuit_breaker = CircuitBreaker(max_retries=3)
        self.stages: Dict[str, callable] = {}
        self._stage_sequence: List[str] = []
        self._init_db()

    def _init_db(self) -> None:
        """Initialize state persistence."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                task_id TEXT PRIMARY KEY,
                state JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def register_stage(self, name: str, func: callable) -> None:
        """Register pipeline stage with explicit ordering."""
        self.stages[name] = func
        if name not in self._stage_sequence:
            self._stage_sequence.append(name)

    def execute(self, task_id: str, initial_data: Dict[str, Any]) -> PipelineState:
        """Execute pipeline with state persistence."""
        state: PipelineState = {
            "task_id": task_id,
            "current_stage": self._stage_sequence[0] if self._stage_sequence else "end",
            "data": initial_data,
            "errors": [],
            "retry_count": {},
            "completed_stages": [],
            "artifacts": []
        }

        self._save_state(state)

        while state["current_stage"] != "end":
            stage_name = state["current_stage"]

            if stage_name not in self.stages:
                state["errors"].append({
                    "stage": stage_name,
                    "error": f"Stage not registered: {stage_name}"
                })
                break

            result = self.circuit_breaker.call(
                self.stages[stage_name],
                stage_name,
                state
            )

            if result.success:
                state["completed_stages"].append(stage_name)
                state["current_stage"] = result.next_stage or self._get_next_stage(stage_name)
            else:
                state["errors"].append({
                    "stage": stage_name,
                    "error": result.error,
                    "timestamp": datetime.now().isoformat()
                })

                if result.next_stage == "error_handler":
                    state["current_stage"] = "error_handler"
                else:
                    state["retry_count"][stage_name] = state["retry_count"].get(stage_name, 0) + 1

            self._save_state(state)

        return state

    def _get_next_stage(self, current: str) -> str:
        """Determine next stage using explicit sequence."""
        try:
            idx = self._stage_sequence.index(current)
            return self._stage_sequence[idx + 1] if idx + 1 < len(self._stage_sequence) else "end"
        except ValueError:
            return "end"

    def _save_state(self, state: PipelineState) -> None:
        """Persist state to SQLite, preserving created_at."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO pipeline_runs (task_id, state, created_at, updated_at)
            VALUES (?, ?, COALESCE((SELECT created_at FROM pipeline_runs WHERE task_id = ?), CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)
            ON CONFLICT(task_id) DO UPDATE SET
                state = excluded.state,
                updated_at = CURRENT_TIMESTAMP
        """, (
            state["task_id"],
            json.dumps(state, default=str),
            state["task_id"]
        ))
        conn.commit()
        conn.close()

    def load_state(self, task_id: str) -> PipelineState:
        """Load persisted state."""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT state FROM pipeline_runs WHERE task_id = ?",
            (task_id,)
        ).fetchone()
        conn.close()

        return json.loads(row[0]) if row else None


# Example usage
def example_pipeline():
    pipeline = StatefulPipeline()

    def analyze_requirements(state: PipelineState) -> Dict:
        return {"requirements": state["data"].get("requirements", [])}

    def generate_code(state: PipelineState) -> Dict:
        import random
        if random.random() < 0.3:
            raise Exception("LLM inference timeout")
        return {"code": "# generated code"}

    def test_code(state: PipelineState) -> Dict:
        return {"tests_passed": True}

    def error_handler(state: PipelineState) -> Dict:
        return {"fallback": "use_cached_result"}

    pipeline.register_stage("analyze", analyze_requirements)
    pipeline.register_stage("generate", generate_code)
    pipeline.register_stage("test", test_code)
    pipeline.register_stage("error_handler", error_handler)

    result = pipeline.execute(
        task_id="task_001",
        initial_data={"requirements": ["Implement auth", "Add logging"]}
    )

    print(f"Completed stages: {result['completed_stages']}")
    print(f"Errors: {len(result['errors'])}")
    print(f"Artifacts: {result['artifacts']}")


if __name__ == "__main__":
    example_pipeline()
