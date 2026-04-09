"""Mission 32: Task classifier — determines complexity and intent from user input.

Returns in <200ms without any LLM call. Uses keyword matching and path
detection only. The result drives whether the main agent handles the task
directly or decomposes it into sub-agent waves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ── Intent keywords ────────────────────────────────────────────────────────

_QUESTION_WORDS = {"what", "how", "why", "when", "where", "who", "which", "explain",
                   "describe", "tell", "show", "list", "is", "are", "does", "do",
                   "can", "could", "should", "would"}

_FIX_WORDS = {"fix", "repair", "correct", "resolve", "patch", "address", "remediate"}
_REVIEW_WORDS = {"review", "audit", "check", "scan", "inspect", "analyze", "analyse",
                 "assess", "evaluate"}
_REFACTOR_WORDS = {"refactor", "restructure", "reorganize", "extract", "simplify",
                   "clean", "improve", "optimize", "rewrite"}
_GENERATE_WORDS = {"generate", "create", "write", "add", "implement", "build", "make"}
_TEST_WORDS = {"test", "tests", "coverage", "spec", "specs", "unittest", "pytest"}
_EXPLAIN_WORDS = {"explain", "describe", "summarize", "understand", "tell me about",
                  "what does", "how does", "walk me through"}

# Patterns that indicate full-codebase scope
_CODEBASE_SIGNALS = re.compile(
    r"\b(everything|entire|whole|all files?|full (codebase|project|repo)|codebase)\b",
    re.IGNORECASE,
)

# Patterns that indicate multi-file scope (directory or glob)
_MULTI_FILE_SIGNALS = re.compile(
    r"(src/|app/|lib/|test[s]?/|\*\*|\*\.|/[a-zA-Z][\w/]*/$|module|package|directory)",
    re.IGNORECASE,
)

# Rough file-path heuristic: contains a slash and a file extension
_PATH_RE = re.compile(r"[\w\-./]+\.[a-zA-Z]{1,6}")


@dataclass
class ClassifiedTask:
    complexity: str          # "simple" | "single_file" | "multi_file" | "full_codebase"
    intent: str              # "question" | "review" | "fix" | "refactor" | "explain"
                             # | "generate" | "test" | "analyze" | "unknown"
    targets: list[str] = field(default_factory=list)
    needs_sub_agents: bool = False
    estimated_agents: int = 0
    plan_needed: bool = False

    @property
    def is_direct(self) -> bool:
        """True when the main agent should handle without sub-agents."""
        return not self.needs_sub_agents


class TaskClassifier:
    """Fast, deterministic task classifier."""

    def classify(self, user_input: str, project_root: Path | None = None) -> ClassifiedTask:
        text = user_input.strip()
        lower = text.lower()
        words = set(lower.split())

        intent = self._detect_intent(lower, words)
        targets = self._extract_targets(text, project_root)
        complexity = self._detect_complexity(lower, targets)
        needs_sub, n_agents = self._needs_sub_agents(complexity, intent)

        return ClassifiedTask(
            complexity=complexity,
            intent=intent,
            targets=targets,
            needs_sub_agents=needs_sub,
            estimated_agents=n_agents,
            plan_needed=needs_sub and n_agents >= 3,
        )

    # ── Private ────────────────────────────────────────────────────────────

    def _detect_intent(self, lower: str, words: set[str]) -> str:
        if _REVIEW_WORDS & words or "/review" in lower:
            return "review"
        if _FIX_WORDS & words:
            return "fix"
        if _REFACTOR_WORDS & words:
            return "refactor"
        if _TEST_WORDS & words:
            return "test"
        if _GENERATE_WORDS & words:
            return "generate"
        if _EXPLAIN_WORDS & {w for w in words}:
            return "explain"
        if words & _QUESTION_WORDS:
            return "question"
        return "analyze"

    def _extract_targets(self, text: str, project_root: Path | None) -> list[str]:
        paths: list[str] = []
        for m in _PATH_RE.finditer(text):
            candidate = m.group(0)
            if project_root:
                abs_path = (project_root / candidate).resolve()
                if abs_path.exists():
                    paths.append(str(abs_path))
                    continue
            # Keep even if not confirmed on disk (it may be symbolic)
            if "/" in candidate or "." in candidate:
                paths.append(candidate)
        return paths

    def _detect_complexity(self, lower: str, targets: list[str]) -> str:
        if _CODEBASE_SIGNALS.search(lower):
            return "full_codebase"
        if _MULTI_FILE_SIGNALS.search(lower):
            return "multi_file"
        # Multiple file targets → multi-file
        if len(targets) > 1:
            return "multi_file"
        # Single confirmed file path → single_file
        if len(targets) == 1:
            return "single_file"
        # No explicit file refs but has slash commands like /review → multi_file
        if lower.startswith("/review") or lower.startswith("/analyze"):
            return "multi_file"
        # Default: simple question
        return "simple"

    def _needs_sub_agents(self, complexity: str, intent: str) -> tuple[bool, int]:
        if complexity == "full_codebase":
            return True, 5
        if complexity == "multi_file" and intent in {"review", "fix", "refactor", "test"}:
            return True, 3
        if complexity == "multi_file" and intent in {"analyze"}:
            return True, 2
        return False, 0
