"""Toolbox — wraps existing Nala subsystems for the agent runtime.

Instead of reimplementing, the toolbox provides a single interface that
the ``AgentManager`` uses to call into indexing, git, analysis,
task ledger, multi-agent, and action execution.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.orchestrator import AgentOrchestrator
    from ..config import Config
    from ..multi_agent.lead import LeadAgent
    from ..tasks.ledger import TaskLedger

log = logging.getLogger("nala.agent_runtime.toolbox")


class Toolbox:
    """Façade over Nala's subsystems."""

    def __init__(
        self,
        config: Config,
        project_root: Path,
        orchestrator: AgentOrchestrator | None = None,
        task_ledger: TaskLedger | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self._orchestrator = orchestrator
        self._task_ledger = task_ledger
        self._lead_agent: LeadAgent | None = None

    @property
    def orchestrator(self) -> AgentOrchestrator | None:
        return self._orchestrator

    def set_orchestrator(self, orch: AgentOrchestrator) -> None:
        self._orchestrator = orch

    @property
    def task_ledger(self) -> TaskLedger | None:
        return self._task_ledger

    def set_task_ledger(self, ledger: TaskLedger) -> None:
        self._task_ledger = ledger

    # ── Path helpers ───────────────────────────────────────────────────

    def _resolve_path(self, path: str) -> Path:
        import os
        if os.path.isabs(path):
            return Path(path)
        return self.project_root / path

    def _is_within_project(self, path: Path) -> bool:
        try:
            return str(path.resolve()).startswith(str(self.project_root.resolve()))
        except Exception:
            return False

    # ── Git ────────────────────────────────────────────────────────────

    def git_diff(self) -> str:
        from ..git_ops import diff_summary
        return diff_summary(self.project_root)

    def git_status(self) -> str:
        from ..git_ops import full_status
        return full_status(self.project_root)

    def git_branch(self) -> str:
        from ..git_ops import branch_info
        return branch_info(self.project_root)

    # ── Task ledger ───────────────────────────────────────────────────

    def create_task(self, objective: str) -> str:
        if self._task_ledger is None:
            return "(task ledger not available)"
        task = self._task_ledger.create_task(objective)
        return task.task_id

    def task_status(self) -> str:
        if self._task_ledger is None:
            return "(task ledger not available)"
        return self._task_ledger.status_text()

    def complete_task(self, summary: str = "") -> str:
        if self._task_ledger is None:
            return "(task ledger not available)"
        task = self._task_ledger.complete_current(summary)
        return f"Task {task.task_id} completed" if task else "No active task"

    # ── Multi-agent ───────────────────────────────────────────────────

    def _ensure_lead(self) -> LeadAgent:
        if self._lead_agent is None:
            from ..multi_agent.lead import LeadAgent
            self._lead_agent = LeadAgent(self.config, str(self.project_root))
        return self._lead_agent

    async def team_start(self, objective: str) -> str:
        lead = self._ensure_lead()
        result = await lead.run(objective)
        return result.final_summary or "Team run completed."

    def team_status(self) -> str:
        if self._lead_agent is None:
            return "No team run active."
        return self._lead_agent.get_status()

    async def team_cancel(self) -> str:
        if self._lead_agent is not None:
            self._lead_agent = None
        return "Team run cancelled."

    def send_worker_message(self, worker_id: str, message: str) -> None:
        """Forward a message to a worker via the message bus."""
        lead = self._ensure_lead()
        lead.bus.send("orchestrator", worker_id, message)

    # ── File tools ─────────────────────────────────────────────────────

    def get_cwd(self) -> str:
        """Return project root path used as default working directory."""
        return str(self.project_root.resolve())

    def read_file(self, path: str, max_lines: int = 2000) -> str:
        """Read a file by relative or absolute path."""
        target = self._resolve_path(path)
        if not target.exists():
            return f"(file not found: {path})"
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > max_lines:
                return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
            return "\n".join(lines)
        except Exception as e:
            return f"(error reading file: {e})"

    def search_code(self, query: str, max_results: int = 40) -> str:
        """Search indexed code using the embedder (BM25 or vector)."""
        if self._orchestrator is None:
            return "(orchestrator not available)"
        emb = self._orchestrator._embedder
        if emb is None or not emb.is_ready():
            return "(index not yet available — run /index first)"
        chunks = emb.retrieve(query, top_k=max_results)
        if not chunks:
            return "(no matches found)"
        parts = []
        for c in chunks:
            header = f"### {c.file_path}:{c.start_line}-{c.end_line}"
            parts.append(f"{header}\n{c.content[:1000]}")
        return "\n\n".join(parts)

    def list_files(self, directory: str = "", max_entries: int = 500) -> str:
        """List files in a directory (relative or absolute)."""
        import os
        target = Path(directory) if directory and os.path.isabs(directory) else (self.project_root / directory if directory else self.project_root)
        if not target.exists():
            return f"(directory not found: {directory})"
        entries = [f"(listing: {target.resolve()})"]
        try:
            for item in sorted(target.iterdir()):
                if item.name.startswith(".") or item.name in ("node_modules", "__pycache__", "target", ".git"):
                    continue
                prefix = "d " if item.is_dir() else "f "
                size = ""
                if item.is_file():
                    sz = item.stat().st_size
                    size = f" ({sz:,}b)" if sz < 100_000 else f" ({sz // 1024}kb)"
                entries.append(f"{prefix}{item.name}{size}")
                if len(entries) >= max_entries:
                    entries.append(f"... (truncated at {max_entries})")
                    break
        except Exception as e:
            return f"(error listing: {e})"
        return "\n".join(entries) if entries else "(empty directory)"

    def write_file(self, path: str, content: str) -> str:
        """Write content to a file inside the project root."""
        target = self._resolve_path(path)
        if not self._is_within_project(target):
            return "(write denied: path is outside project root)"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} chars to {path}"
        except Exception as e:
            return f"(error writing file: {e})"

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        """Replace exact text in a file inside the project root."""
        target = self._resolve_path(path)
        if not target.exists():
            return f"(file not found: {path})"
        if not self._is_within_project(target):
            return "(edit denied: path is outside project root)"
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            if old_text not in content:
                return f"(old_text not found in {path} — no changes made)"
            count = content.count(old_text)
            updated = content.replace(old_text, new_text, 1)
            target.write_text(updated, encoding="utf-8")
            return f"Replaced 1 of {count} occurrence(s) in {path}"
        except Exception as e:
            return f"(error editing file: {e})"

    def tree(self, directory: str = "", max_depth: int = 4, max_entries: int = 500) -> str:
        """Recursive directory listing with depth control (relative or absolute)."""
        import os
        target = Path(directory) if directory and os.path.isabs(directory) else (self.project_root / directory if directory else self.project_root)
        if not target.exists():
            return f"(directory not found: {directory})"
        skip = {"node_modules", "__pycache__", "target", ".git", ".venv",
                "venv", "dist", "build", ".nala", ".mypy_cache", ".next",
                ".ruff_cache", ".pytest_cache", "egg-info"}
        lines: list[str] = [f"({target.resolve()})"]

        def _walk(p: Path, prefix: str, depth: int) -> None:
            if len(lines) >= max_entries or depth > max_depth:
                return
            try:
                children = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except PermissionError:
                return
            items = [e for e in children if e.name not in skip and not e.name.startswith(".")]
            for i, entry in enumerate(items):
                if len(lines) >= max_entries:
                    lines.append(f"{prefix}...")
                    return
                conn = "└── " if i == len(items) - 1 else "├── "
                lines.append(f"{prefix}{conn}{entry.name}{'/' if entry.is_dir() else ''}")
                if entry.is_dir():
                    ext = "    " if i == len(items) - 1 else "│   "
                    _walk(entry, prefix + ext, depth + 1)

        _walk(target, "", 0)
        return "\n".join(lines) if lines else "(empty directory)"

    # ── Analysis ──────────────────────────────────────────────────────

    async def run_analysis(self, perspective: str = "quick") -> str:
        """Run code analysis. perspective: 'quick', 'all', or a specific name."""
        from ..perspectives.engine import PerspectivesEngine, format_results_as_text
        engine = PerspectivesEngine(self.config)
        if perspective == "all":
            results = await engine.run_all(str(self.project_root))
        elif perspective == "quick":
            results = await engine.run_quick(str(self.project_root))
        else:
            one = await engine.run_one(perspective, str(self.project_root))
            results = [one] if one else []
        return format_results_as_text(results)

    # ── Shell / verification ────────────────────────────────────────

    def run_shell(self, command: str, timeout: int = 60, cwd: str = "") -> dict:
        """Run a shell command and return {exit_code, output}."""
        import subprocess
        workdir = self._resolve_path(cwd) if cwd else self.project_root
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(workdir),
                timeout=timeout,
            )
            return {
                "exit_code": result.returncode,
                "output": f"(cwd={workdir})\n" + (result.stdout + result.stderr).strip(),
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "output": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"exit_code": -1, "output": str(e)}

    # ── LLM queries ──────────────────────────────────────────────────

    async def stream_query(self, message: str):
        if self._orchestrator is None:
            yield "(orchestrator not available)"
            return
        async for chunk in self._orchestrator.stream_query(message):
            yield chunk

    async def stream_action_query(self, message: str):
        if self._orchestrator is None:
            yield "(orchestrator not available)"
            return
        async for chunk in self._orchestrator.stream_query_with_actions(message):
            yield chunk
