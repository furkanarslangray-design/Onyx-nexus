#!/usr/bin/env python3
"""E2B sandbox executor for secure code execution.

Routes all generated code to isolated sandboxes. Never executes on host.
"""

import os
import json
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class SandboxProvider(Enum):
    E2B = "e2b"
    DAYTONA = "daytona"
    LOCAL_DOCKER = "local_docker"


@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    artifacts: List[str]
    execution_time_ms: int


class SandboxExecutor:
    """Secure sandbox execution environment."""

    def __init__(self, provider: SandboxProvider = SandboxProvider.E2B):
        self.provider = provider
        self.api_key = os.getenv("E2B_API_KEY") or os.getenv("DAYTONA_API_KEY")
        self.active_sandboxes: Dict[str, Any] = {}

    async def create_sandbox(self, template: str = "base") -> str:
        """Create isolated sandbox instance."""
        if self.provider == SandboxProvider.E2B:
            return await self._create_e2b_sandbox(template)
        elif self.provider == SandboxProvider.DAYTONA:
            return await self._create_daytona_sandbox(template)
        else:
            return await self._create_docker_sandbox(template)

    async def _create_e2b_sandbox(self, template: str) -> str:
        """E2B sandbox creation."""
        try:
            from e2b import Sandbox
            sandbox = await Sandbox.create(template=template, api_key=self.api_key)
            sandbox_id = sandbox.id
            self.active_sandboxes[sandbox_id] = sandbox
            return sandbox_id
        except ImportError:
            raise RuntimeError("e2b package not installed: pip install e2b")

    async def _create_daytona_sandbox(self, template: str) -> str:
        """Daytona sandbox creation."""
        # Placeholder for Daytona SDK integration
        raise NotImplementedError("Daytona integration pending SDK availability")

    async def _create_docker_sandbox(self, template: str) -> str:
        """Local Docker fallback (zero-cost)."""
        import docker
        client = docker.from_env()

        container = client.containers.run(
            image=f"python:3.11-slim",
            command="sleep infinity",
            detach=True,
            remove=True,
            mem_limit="512m",
            cpu_quota=50000,
            network_mode="none"  # Air-gapped
        )

        sandbox_id = container.id
        self.active_sandboxes[sandbox_id] = container
        return sandbox_id

    async def execute_code(
        self,
        sandbox_id: str,
        code: str,
        language: str = "python",
        timeout: int = 30
    ) -> ExecutionResult:
        """Execute code in sandbox with resource limits."""
        import time
        start_time = time.time()

        try:
            if self.provider == SandboxProvider.E2B:
                result = await self._execute_e2b(sandbox_id, code, language, timeout)
            else:
                result = await self._execute_docker(sandbox_id, code, language, timeout)

            result.execution_time_ms = int((time.time() - start_time) * 1000)
            return result

        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                artifacts=[],
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

    async def _execute_e2b(
        self,
        sandbox_id: str,
        code: str,
        language: str,
        timeout: int
    ) -> ExecutionResult:
        """Execute in E2B sandbox."""
        sandbox = self.active_sandboxes.get(sandbox_id)
        if not sandbox:
            raise ValueError(f"Sandbox not found: {sandbox_id}")

        # Write code to file
        filename = f"/tmp/script.{language}"
        await sandbox.files.write(filename, code)

        # Execute with timeout
        process = await sandbox.process.start(f"python {filename}")
        output = await process.wait(timeout=timeout)

        return ExecutionResult(
            success=output.exit_code == 0,
            stdout=output.stdout,
            stderr=output.stderr,
            exit_code=output.exit_code,
            artifacts=[],
            execution_time_ms=0
        )

    async def _execute_docker(
        self,
        sandbox_id: str,
        code: str,
        language: str,
        timeout: int
    ) -> ExecutionResult:
        """Execute in local Docker container."""
        container = self.active_sandboxes.get(sandbox_id)
        if not container:
            raise ValueError(f"Container not found: {sandbox_id}")

        # Write and execute
        exec_result = container.exec_run(
            cmd=["python", "-c", code],
            timeout=timeout
        )

        return ExecutionResult(
            success=exec_result.exit_code == 0,
            stdout=exec_result.output.decode() if exec_result.output else "",
            stderr="",
            exit_code=exec_result.exit_code,
            artifacts=[],
            execution_time_ms=0
        )

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        """Clean up sandbox instance."""
        sandbox = self.active_sandboxes.pop(sandbox_id, None)
        if sandbox:
            if self.provider == SandboxProvider.E2B:
                await sandbox.close()
            else:
                sandbox.stop()


# Circuit breaker integration
class ResilientExecutor:
    """Executor with 3-strike circuit breaker."""

    def __init__(self):
        self.executor = SandboxExecutor()
        self.failure_counts: Dict[str, int] = {}
        self.max_retries = 3

    async def execute_with_retry(
        self,
        code: str,
        language: str = "python"
    ) -> ExecutionResult:
        """Execute with automatic retry and sandbox recreation."""
        sandbox_id = None

        for attempt in range(self.max_retries):
            try:
                if not sandbox_id:
                    sandbox_id = await self.executor.create_sandbox()

                result = await self.executor.execute_code(
                    sandbox_id, code, language
                )

                if result.success:
                    return result

                # Analyze failure for circuit breaker
                self.failure_counts["execute"] = self.failure_counts.get("execute", 0) + 1

                if self.failure_counts["execute"] >= self.max_retries:
                    # Recreate sandbox on persistent failures
                    await self.executor.destroy_sandbox(sandbox_id)
                    sandbox_id = None
                    self.failure_counts["execute"] = 0

            except Exception as e:
                if attempt == self.max_retries - 1:
                    return ExecutionResult(
                        success=False,
                        stdout="",
                        stderr=f"Max retries exceeded: {e}",
                        exit_code=-1,
                        artifacts=[],
                        execution_time_ms=0
                    )

        return ExecutionResult(
            success=False,
            stdout="",
            stderr="Circuit breaker open",
            exit_code=-1,
            artifacts=[],
            execution_time_ms=0
        )


async def main():
    """Example usage."""
    executor = ResilientExecutor()

    code = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(f"fib(10) = {fibonacci(10)}")
"""

    result = await executor.execute_with_retry(code)
    print(f"Success: {result.success}")
    print(f"Output: {result.stdout}")
    print(f"Time: {result.execution_time_ms}ms")


if __name__ == "__main__":
    asyncio.run(main())
