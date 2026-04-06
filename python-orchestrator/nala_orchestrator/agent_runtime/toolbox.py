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

    def git_diff(self, path: str = "") -> str:
        """Return unified diff, optionally scoped to a specific file."""
        import subprocess
        cmd = ["git", "diff", "--", path] if path else ["git", "diff"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=str(self.project_root), timeout=15
            )
            output = (result.stdout + result.stderr).strip()
            if not output:
                return "(no changes — working tree is clean)"
            if len(output) > 20_000:
                output = output[:20_000] + "\n... (diff truncated)"
            return output
        except Exception as e:
            from ..git_ops import diff_summary
            return diff_summary(self.project_root)

    def git_status(self) -> str:
        from ..git_ops import full_status
        return full_status(self.project_root)

    def git_branch(self) -> str:
        from ..git_ops import branch_info
        return branch_info(self.project_root)

    def git_log(self, max_commits: int = 10) -> str:
        """Return formatted recent git commit log."""
        import subprocess
        max_commits = max(1, min(max_commits, 50))
        try:
            result = subprocess.run(
                [
                    "git", "log",
                    f"-{max_commits}",
                    "--pretty=format:%h  %ad  %an  %s",
                    "--date=short",
                ],
                capture_output=True, text=True,
                cwd=str(self.project_root), timeout=15,
            )
            out = (result.stdout + result.stderr).strip()
            return out if out else "(no commits yet)"
        except Exception as e:
            return f"(git log failed: {e})"

    def git_commit(self, message: str, add_all: bool = True) -> str:
        """Stage and commit changes. Returns the new commit hash."""
        import subprocess

        if not message.strip():
            return "(commit message cannot be empty)"

        try:
            if add_all:
                subprocess.run(
                    ["git", "add", "-A"],
                    capture_output=True, text=True,
                    cwd=str(self.project_root), timeout=15, check=True,
                )
            result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True, text=True,
                cwd=str(self.project_root), timeout=30,
            )
            out = (result.stdout + result.stderr).strip()
            if result.returncode == 0:
                return f"Committed: {out}"
            return f"(git commit failed: {out})"
        except subprocess.CalledProcessError as e:
            return f"(git add failed: {e.stderr})"
        except Exception as e:
            return f"(git commit error: {e})"

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
            # Pass the embedder so worker agents get codebase retrieval access.
            embedder = None
            if self._orchestrator is not None:
                embedder = getattr(self._orchestrator, "_embedder", None)
            self._lead_agent = LeadAgent(
                self.config, self.project_root, embedder=embedder
            )
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

    def read_file(
        self,
        path: str,
        max_lines: int = 2000,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> str:
        """Read a file by relative or absolute path with optional line range.

        Returns content with line numbers prepended so the agent can
        reference exact line numbers when calling insert_lines / replace_lines.
        """
        target = self._resolve_path(path)
        if not target.exists():
            return f"(file not found: {path})"
        try:
            all_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            return f"(error reading file: {e})"

        total = len(all_lines)
        s = max(1, start_line) - 1            # 0-based inclusive
        e = (min(end_line, total) if end_line else total)  # 0-based exclusive

        lines = all_lines[s:e]
        if not lines:
            return f"(no lines in range {start_line}–{end_line or total} of {path})"

        # Prepend 1-based line numbers; truncate if huge
        truncated = False
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            truncated = True

        width = len(str(s + len(lines)))
        numbered = "\n".join(
            f"{s + i + 1:>{width}}  {line}" for i, line in enumerate(lines)
        )
        suffix = f"\n... ({total - (s + max_lines)} more lines, use start_line/end_line)" if truncated else ""
        return numbered + suffix

    def file_info(self, path: str) -> str:
        """Return file metadata: size, line count, last modified."""
        import datetime
        target = self._resolve_path(path)
        if not target.exists():
            return f"(file not found: {path})"
        try:
            stat = target.stat()
            line_count = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            size_kb = stat.st_size / 1024
            return (
                f"path:     {target.resolve()}\n"
                f"lines:    {line_count:,}\n"
                f"size:     {size_kb:.1f} KB ({stat.st_size:,} bytes)\n"
                f"modified: {mtime}"
            )
        except Exception as e:
            return f"(error getting file info: {e})"

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

    def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
    ) -> str:
        """Replace exact text in a file inside the project root.

        On mismatch, returns context lines around where the text was expected
        so the agent can see the actual content and correct old_text.
        """
        target = self._resolve_path(path)
        if not target.exists():
            return f"(file not found: {path})"
        if not self._is_within_project(target):
            return "(edit denied: path is outside project root)"
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"(error reading file: {e})"

        if old_text not in content:
            # Helpful context: show the first 60 chars of old_text
            # and up to 20 lines from the beginning of the file so the agent
            # can see the actual indentation / content and correct its match.
            preview_lines = content.splitlines()[:30]
            width = len(str(len(preview_lines)))
            preview = "\n".join(
                f"{i+1:>{width}}  {ln}" for i, ln in enumerate(preview_lines)
            )
            first_line = old_text.splitlines()[0][:80] if old_text else ""
            return (
                f"(old_text not found in {path} — no changes made)\n"
                f"First line of old_text you provided: {first_line!r}\n"
                f"First 30 lines of actual file:\n{preview}"
            )

        count = content.count(old_text)
        if replace_all:
            updated = content.replace(old_text, new_text)
            replaced = count
        else:
            updated = content.replace(old_text, new_text, 1)
            replaced = 1
        try:
            target.write_text(updated, encoding="utf-8")
        except Exception as e:
            return f"(error writing file: {e})"
        suffix = f" ({count - 1} more occurrence(s) not replaced — use replace_all=true if needed)" if count > 1 and not replace_all else ""
        return f"Replaced {replaced} of {count} occurrence(s) in {path}{suffix}"

    def insert_lines(self, path: str, line_number: int, text: str) -> str:
        """Insert text before a specific 1-based line number in a file.

        Use line_number=1 to prepend; 999999 (or any number > total) to append.
        """
        target = self._resolve_path(path)
        if not target.exists():
            return f"(file not found: {path})"
        if not self._is_within_project(target):
            return "(insert denied: path is outside project root)"
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except Exception as e:
            return f"(error reading file: {e})"

        # Ensure text ends with newline so subsequent lines aren't merged
        if text and not text.endswith("\n"):
            text = text + "\n"

        insert_at = max(0, min(line_number - 1, len(lines)))
        lines.insert(insert_at, text)
        try:
            target.write_text("".join(lines), encoding="utf-8")
        except Exception as e:
            return f"(error writing file: {e})"

        n_inserted = text.count("\n")
        return (
            f"Inserted {n_inserted} line(s) before line {line_number} in {path} "
            f"(file now has {len(lines)} lines)"
        )

    def replace_lines(
        self,
        path: str,
        start_line: int,
        end_line: int,
        new_text: str,
    ) -> str:
        """Replace a range of lines in a file (1-based, both inclusive)."""
        target = self._resolve_path(path)
        if not target.exists():
            return f"(file not found: {path})"
        if not self._is_within_project(target):
            return "(replace denied: path is outside project root)"
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except Exception as e:
            return f"(error reading file: {e})"

        total = len(lines)
        s = max(0, start_line - 1)
        e = min(end_line, total)

        if s >= total:
            return f"(start_line {start_line} is beyond end of file ({total} lines))"
        if s > e:
            return f"(start_line {start_line} > end_line {end_line})"

        if not new_text.endswith("\n"):
            new_text = new_text + "\n"

        replaced_count = e - s
        new_lines = lines[:s] + [new_text] + lines[e:]
        try:
            target.write_text("".join(new_lines), encoding="utf-8")
        except Exception as e_:
            return f"(error writing file: {e_})"
        return (
            f"Replaced lines {start_line}–{end_line} ({replaced_count} line(s)) in {path} "
            f"(file now has {len(new_lines)} lines)"
        )

    def find_in_files(
        self,
        pattern: str,
        directory: str = "",
        file_glob: str = "",
        max_results: int = 60,
        ignore_case: bool = False,
    ) -> str:
        """Grep-like regex search across files. Returns file:line:content matches."""
        import fnmatch
        import os
        import re

        target = (
            Path(directory) if directory and os.path.isabs(directory)
            else (self.project_root / directory if directory else self.project_root)
        )
        if not target.exists():
            return f"(directory not found: {directory})"

        skip_dirs = {
            "node_modules", "__pycache__", "target", ".git", ".venv",
            "venv", "dist", "build", ".nala", ".mypy_cache", ".next",
            ".ruff_cache", ".pytest_cache",
        }
        text_exts = {
            ".py", ".rs", ".js", ".ts", ".tsx", ".jsx", ".go", ".java",
            ".c", ".cpp", ".h", ".hpp", ".rb", ".md", ".txt", ".toml",
            ".yaml", ".yml", ".json", ".sh", ".bash", ".zsh", ".env",
            ".css", ".html", ".sql", ".graphql", ".proto",
        }

        flags = re.IGNORECASE if ignore_case else 0
        try:
            rx = re.compile(pattern, flags)
        except re.error as exc:
            return f"(invalid regex: {exc})"

        results: list[str] = []
        for dirpath, dirnames, filenames in os.walk(target):
            # Prune ignored directories in place
            dirnames[:] = [
                d for d in dirnames
                if d not in skip_dirs and not d.startswith(".")
            ]
            for fname in sorted(filenames):
                if fname.startswith("."):
                    continue
                if file_glob and not fnmatch.fnmatch(fname, file_glob):
                    continue
                fpath = Path(dirpath) / fname
                if not file_glob and fpath.suffix.lower() not in text_exts:
                    continue
                if fpath.stat().st_size > 1_000_000:
                    continue
                try:
                    rel = str(fpath.relative_to(self.project_root))
                except ValueError:
                    rel = str(fpath)
                try:
                    for lineno, line in enumerate(
                        fpath.read_text(encoding="utf-8", errors="replace").splitlines(),
                        start=1,
                    ):
                        if rx.search(line):
                            results.append(f"{rel}:{lineno}: {line.rstrip()}")
                            if len(results) >= max_results:
                                results.append(f"... (truncated at {max_results} matches)")
                                return "\n".join(results)
                except OSError:
                    pass

        if not results:
            return f"(no matches for {pattern!r})"
        return "\n".join(results)

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

    # ── Agent delegation ──────────────────────────────────────────────

    async def spawn_worker(self, task: str, label: str = "") -> str:
        """Run a child tool-calling agent for a focused sub-task.

        The child agent gets full tool access and runs its own tool loop.
        Use this to delegate self-contained chunks of work so the parent
        agent's context stays clean.
        """
        from .tool_executor import run_tool_loop
        from ..llm.provider import create_provider

        label = label or "worker"
        system_prompt = (
            f"You are a focused coding agent handling the sub-task: {label}.\n"
            f"You have full tool access. Complete the task, verify your work, "
            f"and report what you did.\n"
            f"Project root: {self.project_root}"
        )
        try:
            provider = create_provider(self.config)
        except Exception as exc:
            return f"(spawn_worker: could not create provider — {exc})"

        chunks: list[str] = []
        try:
            async for chunk in run_tool_loop(
                provider=provider,
                toolbox=self,          # child shares parent's toolbox
                system_prompt=system_prompt,
                user_message=task,
                max_rounds=20,
                max_tokens=4096,
            ):
                chunks.append(chunk)
        except Exception as exc:
            return f"(spawn_worker: tool loop error — {exc})"

        result = "".join(chunks)
        return result[:8000] if result else "(spawn_worker: no output)"

    # ── Progress checkpoints ──────────────────────────────────────────

    def write_checkpoint(self, label: str, content: str) -> str:
        """Write a progress checkpoint to .nala/agent/checkpoints/<label>.md"""
        if not label or not label.strip():
            return "(checkpoint label cannot be empty)"
        checkpoints_dir = self.project_root / ".nala" / "agent" / "checkpoints"
        try:
            checkpoints_dir.mkdir(parents=True, exist_ok=True)
            safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
            path = checkpoints_dir / f"{safe_label}.md"
            path.write_text(f"# Checkpoint: {label}\n\n{content}\n", encoding="utf-8")
            return f"Checkpoint written: {path.relative_to(self.project_root)}"
        except Exception as exc:
            return f"(write_checkpoint error: {exc})"

    def read_checkpoint(self, label: str = "") -> str:
        """Read a checkpoint, or list all checkpoints if label is empty."""
        checkpoints_dir = self.project_root / ".nala" / "agent" / "checkpoints"
        if not checkpoints_dir.exists():
            return "(no checkpoints directory — no checkpoints written yet)"

        if not label:
            files = sorted(checkpoints_dir.glob("*.md"))
            if not files:
                return "(no checkpoints found)"
            lines = ["**Available checkpoints:**"]
            for f in files:
                lines.append(f"  - {f.stem}")
            return "\n".join(lines)

        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        path = checkpoints_dir / f"{safe_label}.md"
        if not path.exists():
            # Try fuzzy match
            matches = list(checkpoints_dir.glob(f"*{safe_label}*.md"))
            if matches:
                path = matches[0]
            else:
                return f"(checkpoint not found: {label})"
        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:
            return f"(read_checkpoint error: {exc})"
