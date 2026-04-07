"""Verification agent for review findings.

Before a raw finding is promoted to a VerifiedFinding it passes through here.
Each rule gets a targeted verification strategy that can disprove false positives
without LLM calls — pure regex / AST / text analysis only.

Design goal: disprove at least 20% of raw findings. Most rule heuristics fire
on broad patterns that need a secondary check to confirm the signal is real.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .models import RawFinding, VerifiedFinding

if TYPE_CHECKING:
    from nala_orchestrator.graph.connection import GraphConnection

# Severity ranking used for confidence boosting
_SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# Directories / file suffixes that warrant lower confidence
_TEST_PATTERNS = re.compile(r"(test|spec|__tests__|fixtures|mocks)", re.IGNORECASE)
_TEST_EXTS = {".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".test.js", ".test.jsx"}


def _is_test_file(file_path: str) -> bool:
    return bool(_TEST_PATTERNS.search(file_path)) or any(
        file_path.endswith(ext) for ext in _TEST_EXTS
    )


def _read_lines(file_path: str) -> list[str]:
    try:
        return Path(file_path).read_text(encoding="utf-8").splitlines()
    except Exception:
        return []


class Verifier:
    def __init__(self, project_root: str, graph: GraphConnection | None = None):
        self.project_root = Path(project_root)
        self.graph = graph

    async def verify(self, finding: RawFinding) -> VerifiedFinding | None:
        """Verify a raw finding. Returns None if disproven."""
        rule = finding.rule_name
        handler = _RULE_VERIFIERS.get(rule, _default_verify)
        return await handler(finding, self)


# ── Rule-specific verifiers ─────────────────────────────────────────────────


async def _verify_hardcoded_secret(
    finding: RawFinding, v: Verifier
) -> VerifiedFinding | None:
    """Disprove if the line is inside a comment, a test file, or an example/docs dir."""
    del v
    lines = _read_lines(finding.file_path)
    if not lines or finding.start_line > len(lines):
        return None  # Can't read file — discard

    line = lines[finding.start_line - 1]
    stripped = line.lstrip()

    # Disprove: line is a comment
    if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
        return None

    # Disprove: value looks like a placeholder (all-uppercase, "your-key-here", etc.)
    placeholder = re.search(
        r'["\']([A-Z_]{5,}|your[_-][a-z\-]+|xxx+|placeholder|changeme|example)["\']',
        line,
        re.IGNORECASE,
    )
    if placeholder:
        return None

    # Disprove: inside a test/fixtures file
    if _is_test_file(finding.file_path):
        return None

    # Disprove: inside docs / examples directories
    if re.search(r"/(docs?|examples?|samples?|demo)/", finding.file_path, re.IGNORECASE):
        return None

    return _make_verified(
        finding,
        "Confirmed: non-placeholder, non-comment credential pattern.",
        confidence=0.95,
    )


async def _verify_stale_closure(
    finding: RawFinding, v: Verifier
) -> VerifiedFinding | None:
    """Disprove if the hook truly uses no external variables (the empty dep array is correct)."""
    del v
    lines = _read_lines(finding.file_path)
    if not lines:
        return None

    # Extract the hook body (simple heuristic: grab up to 15 lines after hook line)
    start = max(0, finding.start_line - 1)
    window = "\n".join(lines[start : start + 15])

    # If the body only contains constants or JSX with no variable refs, dep=[] is fine
    # Disprove: body is trivially short (single expression, no identifiers)
    idents_in_body = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", window)
    jsx_keywords = {
        "useEffect", "useCallback", "useMemo", "return", "const", "let", "var",
        "async", "await", "function", "true", "false", "null", "undefined",
        "console", "log", "void", "new", "this",
    }
    real_idents = [i for i in idents_in_body if i not in jsx_keywords]
    if len(real_idents) < 3:
        # Looks trivially simple — likely fine with empty deps
        return None

    return _make_verified(
        finding,
        (
            f"Hook references {len(real_idents)} identifiers in body; "
            "empty dep array may cause stale closure."
        ),
        confidence=0.75,
    )


async def _verify_missing_cleanup(
    finding: RawFinding, v: Verifier
) -> VerifiedFinding | None:
    """Disprove if removeEventListener appears anywhere in the same useEffect block."""
    del v
    lines = _read_lines(finding.file_path)
    if not lines:
        return None

    # Look in a 30-line window around the finding for cleanup
    start = max(0, finding.start_line - 1)
    window = "\n".join(lines[start : start + 30])

    if "removeEventListener" in window or "cleanup" in window.lower():
        return None  # Cleanup already present

    return _make_verified(finding, "No removeEventListener found in hook body.", confidence=0.85)


async def _verify_silent_fallback(
    finding: RawFinding, v: Verifier
) -> VerifiedFinding | None:
    """Disprove if the fallback is on a trivial UI string (class names, labels)."""
    del v
    lines = _read_lines(finding.file_path)
    if not lines or finding.start_line > len(lines):
        return None

    line = lines[finding.start_line - 1]

    # Disprove: looks like CSS class / style fallback
    if re.search(r'className|style\s*=|"[a-z\-]+"', line, re.IGNORECASE):
        return None

    # Disprove: assigned to a display label / title / placeholder
    if re.search(r"(label|title|placeholder|aria-|alt)\s*=", line, re.IGNORECASE):
        return None

    return _make_verified(finding, "Silent fallback on non-UI value.", confidence=0.8)


async def _verify_empty_catch(
    finding: RawFinding, v: Verifier
) -> VerifiedFinding | None:
    """Confirm the catch block is actually empty (not just one-liner style)."""
    del v
    lines = _read_lines(finding.file_path)
    if not lines or finding.start_line > len(lines):
        return None

    line = lines[finding.start_line - 1]

    # More precise: catch( ){} on one line with nothing in braces
    if re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", line):
        return _make_verified(finding, "One-line empty catch confirmed.", confidence=0.95)

    # Also check Python: except X: \n    pass
    if finding.start_line + 1 <= len(lines):
        next_line = lines[finding.start_line].strip()
        if "except" in line and next_line == "pass":
            return _make_verified(finding, "except ... pass pattern confirmed.", confidence=0.95)

    # The heuristic fired but the block doesn't look empty — disprove
    return None


async def _verify_missing_loading_guard(
    finding: RawFinding, v: Verifier
) -> VerifiedFinding | None:
    """Disprove if the handler already has a loading/disabled check."""
    del v
    lines = _read_lines(finding.file_path)
    if not lines:
        return None

    start = max(0, finding.start_line - 1)
    window = "\n".join(lines[start : start + 10])

    if re.search(r"isLoading|disabled|loading\s*===?\s*true|isFetching", window, re.IGNORECASE):
        return None

    return _make_verified(finding, "No loading guard detected in handler prelude.", confidence=0.7)


async def _verify_unused_import(
    finding: RawFinding, v: Verifier
) -> VerifiedFinding | None:
    """Confirm the import identifier never appears in the file body."""
    del v
    if not finding.identifiers:
        return None

    lines = _read_lines(finding.file_path)
    if not lines:
        return None

    import_line_idx = finding.start_line - 1

    for ident in finding.identifiers:
        # Count occurrences outside the import line
        occurrences = [
            i for i, ln in enumerate(lines)
            if i != import_line_idx and re.search(r"\b" + re.escape(ident) + r"\b", ln)
        ]
        if occurrences:
            return None  # Used somewhere — not actually unused

    return _make_verified(
        finding,
        f"Identifier(s) {', '.join(finding.identifiers)} not referenced outside import line.",
        confidence=0.9,
    )


async def _verify_stale_todo(
    finding: RawFinding, v: Verifier
) -> VerifiedFinding | None:
    """Always pass through — stale TODOs are low-confidence info items."""
    del v
    lines = _read_lines(finding.file_path)
    if not lines or finding.start_line > len(lines):
        return None
    line = lines[finding.start_line - 1]
    # Disprove: TODO has an issue number link (it's tracked)
    if re.search(r"#\d{3,}|https?://|JIRA-|GH-|LINEAR-", line, re.IGNORECASE):
        return None
    return _make_verified(
        finding,
        "Unlinked TODO/FIXME with no issue reference.",
        confidence=0.6,
    )


async def _default_verify(
    finding: RawFinding, v: Verifier
) -> VerifiedFinding | None:
    """Fallback: pass finding through with base confidence."""
    del v
    return _make_verified(
        finding,
        f"Passed default verification for rule '{finding.rule_name}'.",
        confidence=0.8,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_verified(
    finding: RawFinding,
    evidence: str,
    confidence: float,
) -> VerifiedFinding:
    return VerifiedFinding(
        rule_name=finding.rule_name,
        category=finding.category,
        severity=finding.severity,
        file_path=finding.file_path,
        start_line=finding.start_line,
        end_line=finding.end_line,
        description=finding.description,
        instruction=finding.instruction,
        identifiers=finding.identifiers,
        context=finding.context,
        evidence=evidence,
        confidence=confidence,
    )


_RULE_VERIFIERS = {
    "hardcoded-secret": _verify_hardcoded_secret,
    "stale-closure": _verify_stale_closure,
    "missing-cleanup": _verify_missing_cleanup,
    "silent-fallback": _verify_silent_fallback,
    "empty-catch": _verify_empty_catch,
    "missing-loading-guard": _verify_missing_loading_guard,
    "unused-import": _verify_unused_import,
    "stale-todo": _verify_stale_todo,
}
