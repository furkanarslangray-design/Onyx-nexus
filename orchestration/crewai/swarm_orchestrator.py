#!/usr/bin/env python3
"""CrewAI multi-agent swarm orchestrator for Nexus R&D Factory.

Implements SLEDGEHAMMER mode: deconstructs complex tasks into DAGs,
distributes across specialized workers, aggregates outputs.
"""

import os
import json
import time
import threading
from typing import List, Dict, Any, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import networkx as nx


class AgentRole(Enum):
    ARCHITECT = "architect"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    RESEARCHER = "researcher"
    OPTIMIZER = "optimizer"


@dataclass
class Task:
    id: str
    description: str
    role: AgentRole
    dependencies: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    retries: int = 0
    max_retries: int = 3


@dataclass
class WorkerAgent:
    role: AgentRole
    model_endpoint: str = "http://localhost:8000/v1"
    temperature: float = 0.2
    max_tokens: int = 4096

    def execute(self, task: Task) -> Dict[str, Any]:
        """Execute task via LLM inference with circuit breaker."""
        for attempt in range(task.max_retries):
            try:
                result = self._call_llm(task)
                task.status = "completed"
                return {"status": "success", "output": result, "attempts": attempt + 1}
            except Exception as e:
                task.retries += 1
                if task.retries >= task.max_retries:
                    task.status = "failed"
                    return {
                        "status": "failed",
                        "error": str(e),
                        "root_cause": self._analyze_failure(e),
                        "attempts": attempt + 1
                    }
        return {"status": "failed", "error": "max_retries_exceeded"}

    def _call_llm(self, task: Task) -> str:
        """Call LLM via proxy pool."""
        import requests

        payload = {
            "model": "default",
            "messages": [
                {"role": "system", "content": f"You are a {self.role.value} agent."},
                {"role": "user", "content": task.description}
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }

        response = requests.post(
            f"{self.model_endpoint}/chat/completions",
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _analyze_failure(self, error: Exception) -> str:
        """Root cause analysis for circuit breaker."""
        error_str = str(error).lower()
        if "timeout" in error_str:
            return "network_timeout: increase timeout or switch tier"
        elif "rate_limit" in error_str or "429" in error_str:
            return "rate_limit: rotate session token"
        elif "context_length" in error_str:
            return "context_overflow: split task into smaller chunks"
        else:
            return f"unknown: {type(error).__name__}"


class SwarmOrchestrator:
    """DAG-based multi-agent orchestrator with dependency-aware execution."""

    def __init__(self, max_workers: int = 4):
        self.tasks: Dict[str, Task] = {}
        self.graph = nx.DiGraph()
        self.agents: Dict[AgentRole, WorkerAgent] = {
            role: WorkerAgent(role=role) for role in AgentRole
        }
        self.max_workers = max_workers
        self._completed: Set[str] = set()
        self._lock = threading.Lock()

    def add_task(self, task: Task) -> None:
        """Add task to DAG."""
        self.tasks[task.id] = task
        self.graph.add_node(task.id, role=task.role.value)

        for dep in task.dependencies:
            self.graph.add_edge(dep, task.id)

    def topological_sort(self) -> List[str]:
        """Return execution order respecting dependencies."""
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXUnfeasible:
            raise ValueError("Cycle detected in task DAG")

    def execute(self, callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Execute all tasks with dependency-aware parallelization."""
        execution_order = self.topological_sort()
        results: Dict[str, Any] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures: Dict[str, Any] = {}
            submitted: Set[str] = set()

            while len(submitted) < len(execution_order):
                for task_id in execution_order:
                    if task_id in submitted:
                        continue

                    task = self.tasks[task_id]
                    deps_completed = all(
                        dep in self._completed for dep in task.dependencies
                    )

                    if deps_completed:
                        agent = self.agents[task.role]
                        future = executor.submit(agent.execute, task)
                        futures[task_id] = future
                        submitted.add(task_id)

                # Collect completed futures
                done = [tid for tid, fut in futures.items() if fut.done()]
                for tid in done:
                    if tid not in self._completed:
                        result = futures[tid].result()
                        results[tid] = result
                        with self._lock:
                            self._completed.add(tid)
                        if callback:
                            callback(tid, result)
                        del futures[tid]

                if not done:
                    time.sleep(0.1)

            # Collect any remaining
            for task_id, future in futures.items():
                result = future.result()
                results[task_id] = result
                with self._lock:
                    self._completed.add(task_id)

        return results

    def get_critical_path(self) -> List[str]:
        """Identify critical path for optimization."""
        if not self.graph.edges:
            return []
        return nx.dag_longest_path(self.graph)


def example_usage():
    """Example: Multi-agent code generation pipeline."""
    orchestrator = SwarmOrchestrator(max_workers=4)

    tasks = [
        Task(id="design", description="Design system architecture", role=AgentRole.ARCHITECT),
        Task(id="implement", description="Implement core modules", role=AgentRole.CODER, dependencies=["design"]),
        Task(id="test", description="Generate unit tests", role=AgentRole.TESTER, dependencies=["implement"]),
        Task(id="review", description="Security audit", role=AgentRole.REVIEWER, dependencies=["implement"]),
        Task(id="optimize", description="Performance optimization", role=AgentRole.OPTIMIZER, dependencies=["review", "test"]),
    ]

    for task in tasks:
        orchestrator.add_task(task)

    print(f"Execution order: {orchestrator.topological_sort()}")
    print(f"Critical path: {orchestrator.get_critical_path()}")

    def progress_callback(task_id: str, result: Dict):
        status = result.get("status")
        print(f"[{status.upper()}] {task_id}")

    results = orchestrator.execute(callback=progress_callback)

    successful = sum(1 for r in results.values() if r.get("status") == "success")
    print(f"\nCompleted: {successful}/{len(results)} tasks")


if __name__ == "__main__":
    example_usage()
