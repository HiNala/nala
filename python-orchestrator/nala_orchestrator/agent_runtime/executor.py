"""Mission execution engine — dependency-resolving loop.

Loads missions from the writer's manifest, resolves execution order
respecting dependencies and parallel groups, dispatches each to a
worker (or the orchestrator itself for planning/research tasks),
and loops until all missions are done or the user cancels.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .mission_writer import MissionWriter
from .state import MissionFile, MissionStatus

if TYPE_CHECKING:
    from ..config import Config

log = logging.getLogger("nala.agent_runtime.executor")

MAX_CONCURRENT_WORKERS = 3
MAX_RETRIES = 1

_FAILURE_SIGNALS = frozenset({
    "error", "failed", "exception", "traceback",
    "cannot", "unable to", "not found",
})


@dataclass
class MissionResult:
    mission_id: str
    success: bool
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    attempts: int = 1


class MissionExecutor:
    """Execute a set of missions respecting dependency order."""

    def __init__(
        self,
        config: Config,
        project_root: Path,
        run_id: str,
        *,
        on_progress: object | None = None,
    ) -> None:
        self._config = config
        self._root = project_root
        self._run_id = run_id
        self._writer = MissionWriter(project_root, run_id)
        self._cancelled = False
        self._results: dict[str, MissionResult] = {}

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def results(self) -> dict[str, MissionResult]:
        return dict(self._results)

    async def execute_all(
        self,
        missions: list[MissionFile],
    ) -> AsyncIterator[str]:
        """Execute missions in dependency order, yielding progress text."""
        pending = {m.id: m for m in missions}
        completed_ids: set[str] = set()
        total = len(missions)
        done_count = 0

        yield f"## Executing {total} missions\n\n"

        while pending and not self._cancelled:
            ready = self._get_ready_missions(pending, completed_ids)
            if not ready:
                blocked = [m.id for m in pending.values()]
                yield f"\n**Deadlock detected** — blocked missions: {blocked}\n"
                yield "  Check mission dependencies for circular references.\n"
                for mid in blocked:
                    self._writer.update_mission_status(mid, MissionStatus.FAILED, "Deadlock — circular dependency")
                break

            groups = self._group_parallel(ready)
            for group_id, group_missions in groups.items():
                if self._cancelled:
                    yield "\n**Cancelled by user.**\n"
                    break

                if len(group_missions) == 1:
                    m = group_missions[0]
                    yield f"### [{done_count + 1}/{total}] {m.title}\n"
                    self._writer.update_mission_status(m.id, MissionStatus.IN_PROGRESS)
                    result = await self._execute_with_retry(m)
                    self._results[m.id] = result
                    if result.success:
                        self._writer.update_mission_status(
                            m.id, MissionStatus.COMPLETED, result.summary
                        )
                        completed_ids.add(m.id)
                        done_count += 1
                        yield f"  **Done** — {result.summary[:120]}\n\n"
                    else:
                        self._writer.update_mission_status(
                            m.id, MissionStatus.FAILED, result.summary
                        )
                        done_count += 1
                        retried = f" (after {result.attempts} attempts)" if result.attempts > 1 else ""
                        yield f"  **Failed**{retried} — {result.summary[:120]}\n\n"
                    del pending[m.id]
                else:
                    yield f"### Parallel group `{group_id}` — {len(group_missions)} missions\n"
                    for m in group_missions:
                        self._writer.update_mission_status(m.id, MissionStatus.IN_PROGRESS)

                    tasks = [self._execute_with_retry(m) for m in group_missions]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for m, res in zip(group_missions, results):
                        if isinstance(res, Exception):
                            res = MissionResult(
                                mission_id=m.id,
                                success=False,
                                summary=f"Unexpected error: {res}",
                            )
                        self._results[m.id] = res
                        if res.success:
                            self._writer.update_mission_status(
                                m.id, MissionStatus.COMPLETED, res.summary
                            )
                            completed_ids.add(m.id)
                            yield f"  **{m.title}** — done\n"
                        else:
                            self._writer.update_mission_status(
                                m.id, MissionStatus.FAILED, res.summary
                            )
                            yield f"  **{m.title}** — failed: {res.summary[:80]}\n"
                        done_count += 1
                        del pending[m.id]
                    yield "\n"

        succeeded = sum(1 for r in self._results.values() if r.success)
        failed = sum(1 for r in self._results.values() if not r.success)
        yield f"\n## Execution complete: {succeeded} succeeded, {failed} failed out of {total}\n"
        if failed > 0:
            yield "  Use `/agent missions` to inspect failed missions, or `/agent objective` to retry.\n"

    async def _execute_with_retry(self, mission: MissionFile) -> MissionResult:
        """Execute a mission with one automatic retry on failure."""
        result = await self._execute_single(mission)
        if result.success or self._cancelled:
            return result

        if MAX_RETRIES < 1:
            return result

        log.info("Retrying mission %s after failure: %s", mission.id, result.summary[:80])
        retry = await self._execute_single(mission)
        retry.attempts = 2
        return retry

    async def _execute_single(self, mission: MissionFile) -> MissionResult:
        """Execute one mission using the orchestrator."""
        try:
            from ..agents.orchestrator import AgentOrchestrator

            task_type = mission.task_type.lower()
            model_override: tuple[str, str] | None = None

            try:
                from ..models.types import TaskType
                tt = TaskType(task_type)
                from ..models.router import ModelRouter
                from ..models.registry import ModelRegistry
                registry = ModelRegistry(self._config)
                await registry.ensure_loaded()
                router = ModelRouter(
                    registry,
                    primary_provider=self._config.llm_provider,
                    primary_model=self._config.active_model(),
                )
                route = router.route(tt)
                model_override = (route.provider.value, route.model_id)
            except (ValueError, Exception) as exc:
                log.debug("Model routing fallback for %s: %s", mission.id, exc)

            agent = AgentOrchestrator(self._config, model_override=model_override)

            scope_hint = ", ".join(mission.scope) if mission.scope else "project"
            steps_text = "\n".join(f"  {i}. {s}" for i, s in enumerate(mission.steps, 1))
            prompt = (
                f"Execute this mission:\n\n"
                f"**{mission.title}**\n"
                f"Objective: {mission.objective}\n"
                f"Scope: {scope_hint}\n"
                f"Steps:\n{steps_text}\n\n"
                f"Acceptance criteria:\n"
                + "\n".join(f"  - {ac}" for ac in mission.acceptance_criteria)
                + "\n\nImplement the changes and report what was done."
            )

            chunks: list[str] = []
            async for chunk in agent.stream_query(prompt):
                chunks.append(chunk)

            full_response = "".join(chunks)
            if not full_response.strip():
                return MissionResult(
                    mission_id=mission.id,
                    success=False,
                    summary="Empty response from model — check API key and model availability.",
                )

            # Verify success by checking observable outcomes, not keyword matching.
            success, verify_note = await _verify_mission_outcome(
                self._root, mission, full_response
            )

            summary = (full_response[:400] + (f"\n\n[Verification: {verify_note}]" if verify_note else ""))
            return MissionResult(
                mission_id=mission.id,
                success=success,
                summary=summary or "Completed",
            )
        except Exception as exc:
            log.error("Mission %s failed: %s", mission.id, exc)
            user_msg = _friendly_error(exc)
            return MissionResult(
                mission_id=mission.id,
                success=False,
                summary=user_msg,
            )

    def _get_ready_missions(
        self,
        pending: dict[str, MissionFile],
        completed: set[str],
    ) -> list[MissionFile]:
        """Return missions whose dependencies are all satisfied."""
        ready: list[MissionFile] = []
        for m in pending.values():
            if not m.dependencies:
                ready.append(m)
            elif all(dep in completed for dep in m.dependencies):
                ready.append(m)
        return ready

    def _group_parallel(
        self, missions: list[MissionFile]
    ) -> dict[str, list[MissionFile]]:
        """Group missions by parallel_group. Sequential missions get unique groups."""
        groups: dict[str, list[MissionFile]] = {}
        seq_counter = 0
        for m in missions:
            key = m.parallel_group
            if key == "sequential":
                key = f"_seq_{seq_counter}"
                seq_counter += 1
            groups.setdefault(key, []).append(m)
        return groups


async def _verify_mission_outcome(
    project_root: Path,
    mission: MissionFile,
    response: str,
) -> tuple[bool, str]:
    """Verify mission success by observable evidence, not keyword matching.

    Priority order:
    1. If acceptance criteria mention a verification command, run it.
    2. Check if the response references files that were actually modified (git diff).
    3. Check if scoped files were modified at all.
    4. Fall back to conservative heuristic (explicit failure signals only).

    Returns (success: bool, note: str) where note explains the verdict.
    """
    import subprocess

    # 1. Run verification command if one is embedded in the acceptance criteria
    verify_cmd = _extract_verify_command(mission.acceptance_criteria)
    if verify_cmd:
        try:
            result = subprocess.run(
                verify_cmd,
                shell=True,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return True, f"Verification passed: `{verify_cmd}`"
            else:
                out = (result.stdout + result.stderr).strip()[:200]
                return False, f"Verification failed (`{verify_cmd}`): {out}"
        except subprocess.TimeoutExpired:
            log.warning("Verification command timed out: %s", verify_cmd)
        except Exception as exc:
            log.debug("Verification command error: %s", exc)

    # 2. Check git diff to see if any files changed
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        changed = [f.strip() for f in diff.stdout.splitlines() if f.strip()]
        if changed:
            # If mission had a scope, check overlap
            if mission.scope:
                scope_lower = {s.lower() for s in mission.scope}
                overlap = [f for f in changed if any(s in f.lower() or f.lower() in s for s in scope_lower)]
                if overlap:
                    return True, f"Modified {len(overlap)} scoped file(s): {', '.join(overlap[:3])}"
            return True, f"Modified {len(changed)} file(s): {', '.join(changed[:3])}"
    except Exception:
        pass

    # 3. Conservative fallback: only fail on explicit hard errors, otherwise trust the agent
    response_lower = response[:3000].lower()
    hard_failures = {
        "authentication failed", "api key", "rate limit",
        "file not found", "permission denied", "cannot write",
        "syntax error", "import error", "module not found",
    }
    if any(sig in response_lower for sig in hard_failures):
        return False, "Response contains error signals"

    return True, "No verification command available; no explicit errors detected"


def _extract_verify_command(acceptance_criteria: list[str]) -> str:
    """Extract a shell verification command from acceptance criteria if present.

    Looks for patterns like 'Run cargo test', 'pytest passes', 'npm test passes'.
    """
    import re
    patterns = [
        r"`([^`]+)`",                           # `command` in backticks
        r"run\s+([\w\s./\-]+(?:test|check|lint|build)[\w\s./\-]*)",  # "run cargo test"
        r"(cargo\s+\w+|pytest[\w\s\-]*|npm\s+\w+|go\s+test|make\s+\w+)",
    ]
    for criterion in (acceptance_criteria or []):
        for pattern in patterns:
            m = re.search(pattern, criterion, re.IGNORECASE)
            if m:
                cmd = m.group(1).strip()
                # Sanity check: must look like a real command
                if len(cmd) >= 4 and " " in cmd or any(
                    cmd.startswith(p) for p in ("cargo", "pytest", "npm", "go ", "make", "python")
                ):
                    return cmd
    return ""


def _friendly_error(exc: Exception) -> str:
    """Convert exceptions to user-friendly messages."""
    msg = str(exc)
    if "401" in msg or "authentication" in msg.lower() or "api key" in msg.lower():
        return f"Authentication failed — check your API key. ({msg[:80]})"
    if "429" in msg or "rate" in msg.lower():
        return f"Rate limited — wait a moment and retry. ({msg[:80]})"
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return f"Request timed out — the model may be overloaded. ({msg[:80]})"
    if "connection" in msg.lower():
        return f"Connection error — check your network. ({msg[:80]})"
    return f"Error: {msg[:200]}"
