"""
Duplication perspective.

Detects copy-paste code by normalising function bodies and comparing
structural hashes. Works on Python, Rust, JavaScript, and TypeScript
without requiring Neo4j or Tree-sitter at runtime.

Algorithm:
  1. Extract function bodies using lightweight regex (not full AST).
  2. Normalise: collapse whitespace, replace identifiers with VAR,
     string literals with STR, numeric literals with NUM.
  3. Hash the normalised body.
  4. Group functions by hash — groups of 2+ are duplication clusters.

This catches verbatim copy-paste and near-identical functions (variable
renames, string changes) but not structural paraphrasing.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..sessions.report import Finding
from .base import BasePerspective, PerspectiveResult

if TYPE_CHECKING:
    pass

# Minimum body length (characters) worth hashing — avoids trivial getters
_MIN_BODY_CHARS = 80
# Minimum cluster size to report
_MIN_CLUSTER_SIZE = 2


@dataclass
class FunctionEntry:
    name: str
    file_path: str
    start_line: int
    body: str
    struct_hash: str = field(default="")


class DuplicationPerspective(BasePerspective):
    """Detects copy-paste duplication via structural hashing of function bodies."""

    @property
    def name(self) -> str:
        return "duplication"

    @property
    def description(self) -> str:
        return "Finds copy-pasted code by comparing normalised function bodies"

    async def analyze(self, project_root: str) -> PerspectiveResult:
        start = time.monotonic()
        root = Path(project_root)

        # Collect all functions
        functions: list[FunctionEntry] = []
        for path in _iter_source_files(root):
            rel = str(path.relative_to(root))
            try:
                src = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lang = _detect_lang(path.suffix)
            functions.extend(_extract_functions(src, rel, lang))

        # Group by structural hash
        clusters: dict[str, list[FunctionEntry]] = defaultdict(list)
        for fn in functions:
            if fn.struct_hash:
                clusters[fn.struct_hash].append(fn)

        # Report clusters with 2+ members
        findings: list[Finding] = []
        duplicate_clusters = [
            v for v in clusters.values() if len(v) >= _MIN_CLUSTER_SIZE
        ]
        for cluster in sorted(duplicate_clusters, key=lambda c: -len(c)):
            names = ", ".join(f"`{fn.name}`" for fn in cluster)
            locations = "; ".join(
                f"{fn.file_path}:{fn.start_line}" for fn in cluster
            )
            findings.append(Finding(
                title=f"Duplicate code: {len(cluster)} identical functions",
                description=(
                    f"Functions {names} have structurally identical bodies. "
                    f"Locations: {locations}. "
                    "This violates DRY and means bug fixes must be applied multiple times."
                ),
                file_path=cluster[0].file_path,
                start_line=cluster[0].start_line,
                severity=_severity(len(cluster)),
                perspective=self.name,
                suggestion=(
                    f"Extract the shared logic into a single function and call it from "
                    f"all {len(cluster)} sites."
                ),
            ))

        duration_ms = int((time.monotonic() - start) * 1000)
        return PerspectiveResult(
            perspective_name=self.name,
            findings=findings,
            summary=(
                f"Found {len(duplicate_clusters)} duplication clusters "
                f"({sum(len(c) for c in duplicate_clusters)} functions affected)."
            ),
            duration_ms=duration_ms,
        )


# ── Extraction ─────────────────────────────────────────────────────────────

def _extract_functions(src: str, rel_path: str, lang: str) -> list[FunctionEntry]:
    """Extract function bodies using language-specific regex."""
    if lang == "python":
        return _extract_python(src, rel_path)
    if lang in ("rust",):
        return _extract_rust(src, rel_path)
    if lang in ("javascript", "typescript"):
        return _extract_js(src, rel_path)
    return []


_PY_FUNC = re.compile(
    r"^(\s*)def\s+(\w+)\s*\([^)]*\)\s*(?:->[^:]+)?:",
    re.MULTILINE,
)

def _extract_python(src: str, rel_path: str) -> list[FunctionEntry]:
    entries = []
    lines = src.splitlines()
    for m in _PY_FUNC.finditer(src):
        indent = len(m.group(1))
        name = m.group(2)
        start_line = src[:m.start()].count("\n") + 1
        body_lines = []
        # Collect body: lines more indented than the def
        for line in lines[start_line:]:  # start_line is 1-based, list is 0-based
            if line.strip() == "":
                body_lines.append(line)
                continue
            if len(line) - len(line.lstrip()) <= indent and line.strip():
                break
            body_lines.append(line)
        body = "\n".join(body_lines)
        if len(body) >= _MIN_BODY_CHARS:
            entry = FunctionEntry(name=name, file_path=rel_path,
                                  start_line=start_line, body=body)
            entry.struct_hash = _struct_hash(body)
            entries.append(entry)
    return entries


_RS_FUNC = re.compile(
    r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*[<(]",
    re.MULTILINE,
)

def _extract_rust(src: str, rel_path: str) -> list[FunctionEntry]:
    entries = []
    for m in _RS_FUNC.finditer(src):
        name = m.group(1)
        start_line = src[:m.start()].count("\n") + 1
        # Find the function body: first '{' after the match, then balanced braces
        body_start = src.find("{", m.end())
        if body_start == -1:
            continue
        body = _extract_braced(src, body_start)
        if body and len(body) >= _MIN_BODY_CHARS:
            entry = FunctionEntry(name=name, file_path=rel_path,
                                  start_line=start_line, body=body)
            entry.struct_hash = _struct_hash(body)
            entries.append(entry)
    return entries


_JS_FUNC = re.compile(
    r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()",
    re.MULTILINE,
)

def _extract_js(src: str, rel_path: str) -> list[FunctionEntry]:
    entries = []
    for m in _JS_FUNC.finditer(src):
        name = m.group(1) or m.group(2) or "anonymous"
        start_line = src[:m.start()].count("\n") + 1
        body_start = src.find("{", m.end())
        if body_start == -1:
            continue
        body = _extract_braced(src, body_start)
        if body and len(body) >= _MIN_BODY_CHARS:
            entry = FunctionEntry(name=name, file_path=rel_path,
                                  start_line=start_line, body=body)
            entry.struct_hash = _struct_hash(body)
            entries.append(entry)
    return entries


def _extract_braced(src: str, open_pos: int) -> str:
    """Extract the content of a brace-delimited block starting at open_pos."""
    depth = 0
    for i in range(open_pos, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_pos:i + 1]
    return ""


# ── Normalisation ──────────────────────────────────────────────────────────

_STR_LIT  = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\'')
_NUM_LIT  = re.compile(r'\b\d+\.?\d*\b')
_IDENT    = re.compile(r'\b[a-zA-Z_]\w*\b')
_WS       = re.compile(r'\s+')

# Keywords to preserve (don't replace with VAR)
_KEYWORDS = frozenset({
    "if", "else", "elif", "for", "while", "return", "match", "case",
    "let", "mut", "fn", "pub", "struct", "impl", "trait", "use",
    "const", "static", "async", "await", "def", "class", "import",
    "from", "with", "try", "except", "raise", "pass", "break",
    "continue", "and", "or", "not", "in", "is", "true", "false",
    "True", "False", "None", "null", "undefined", "self", "Self",
    "function", "var",
})


def _normalise(body: str) -> str:
    """Normalise a function body for structural comparison."""
    body = _STR_LIT.sub("STR", body)
    body = _NUM_LIT.sub("NUM", body)
    body = _IDENT.sub(lambda m: m.group(0) if m.group(0) in _KEYWORDS else "VAR", body)
    body = _WS.sub(" ", body)
    return body.strip()


def _struct_hash(body: str) -> str:
    normalised = _normalise(body)
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]


# ── Helpers ────────────────────────────────────────────────────────────────

_SOURCE_EXTS = {".py", ".rs", ".js", ".ts", ".jsx", ".tsx"}
_SKIP_DIRS   = {"node_modules", "target", ".git", "__pycache__", ".venv",
                "venv", "dist", "build", ".nala"}


def _iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(p in _SKIP_DIRS for p in path.parts):
            continue
        if path.suffix in _SOURCE_EXTS:
            yield path


def _detect_lang(suffix: str) -> str:
    return {
        ".py": "python", ".rs": "rust",
        ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
    }.get(suffix, "")


def _severity(cluster_size: int) -> str:
    if cluster_size >= 5:
        return "high"
    if cluster_size >= 3:
        return "medium"
    return "low"
