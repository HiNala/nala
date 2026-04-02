"""
Dependency perspective.

Maps import/dependency relationships between files and flags:
  - Circular import cycles (always bad)
  - High fan-out files (import too many things — fragile to change)
  - High fan-in files (too many things depend on them — risky to modify)

Works in two modes:
  Graph mode (Neo4j): uses IMPORTS/DEPENDS_ON relationships for full accuracy.
  Heuristic mode: parses import statements with regex from all source files.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from ..sessions.report import Finding
from .base import BasePerspective, PerspectiveResult

if TYPE_CHECKING:
    pass

_SKIP_DIRS = {
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".nala",
}
_SOURCE_EXTS = {".py", ".rs", ".js", ".ts", ".jsx", ".tsx"}

# Thresholds
_HIGH_FAN_OUT = 15   # imports this many or more modules
_HIGH_FAN_IN  = 10   # this many files import it


class DependencyPerspective(BasePerspective):
    """Maps import graph and flags circular deps and high coupling."""

    @property
    def name(self) -> str:
        return "dependency"

    @property
    def description(self) -> str:
        return "Maps import graph; flags circular dependencies and tight coupling"

    def requires_graph(self) -> bool:
        return False  # heuristic fallback available

    async def analyze(self, project_root: str) -> PerspectiveResult:
        start = time.monotonic()

        if self.graph and self.graph.is_available():
            findings = await self._analyze_via_graph()
        else:
            findings = self._analyze_heuristic(project_root)

        duration_ms = int((time.monotonic() - start) * 1000)
        return PerspectiveResult(
            perspective_name=self.name,
            findings=findings,
            summary=_summarize(findings),
            duration_ms=duration_ms,
        )

    # ── Graph mode ─────────────────────────────────────────────────────────

    async def _analyze_via_graph(self) -> list[Finding]:
        from ..graph.queries import find_circular_dependencies, find_high_coupling
        findings = []

        # Circular dependencies
        cypher, params = find_circular_dependencies()
        for row in self.graph.run(cypher, **params):
            cycle = row.get("cycle", "unknown")
            findings.append(Finding(
                title=f"Circular dependency: {cycle}",
                description=(
                    f"A circular import cycle exists: {cycle}. "
                    "Circular imports make it impossible to reason about load order "
                    "and cause subtle bugs in lazy-loading environments."
                ),
                file_path=cycle.split(" → ")[0] if " → " in cycle else "",
                start_line=0,
                severity="high",
                perspective=self.name,
                suggestion=(
                    "Break the cycle by extracting shared code into a common module "
                    "that neither side imports."
                ),
            ))

        # High coupling
        cypher, params = find_high_coupling(fan_out=_HIGH_FAN_OUT, fan_in=_HIGH_FAN_IN)
        for row in self.graph.run(cypher, **params):
            findings.append(_coupling_finding(row, self.name))

        return findings

    # ── Heuristic mode ─────────────────────────────────────────────────────

    def _analyze_heuristic(self, project_root: str) -> list[Finding]:
        root = Path(project_root)
        source_files = list(_iter_source_files(root))

        # Build file → set of imported modules map
        imports: dict[str, set[str]] = defaultdict(set)
        for path in source_files:
            rel = str(path.relative_to(root))
            lang = _detect_lang(path.suffix)
            try:
                src = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for mod in _extract_imports(src, lang):
                imports[rel].add(mod)

        # Build reverse map: module → files that import it
        imported_by: dict[str, set[str]] = defaultdict(set)
        for file_rel, mods in imports.items():
            for mod in mods:
                imported_by[mod].add(file_rel)

        findings: list[Finding] = []

        # Detect cycles using DFS
        cycles = _find_cycles(imports)
        for cycle in cycles[:10]:  # cap at 10
            path_str = " → ".join(cycle)
            findings.append(Finding(
                title=f"Circular import: {cycle[0]}",
                description=(
                    f"Import cycle detected: {path_str}. "
                    "Circular imports prevent proper module isolation and can "
                    "cause import errors in certain Python configurations."
                ),
                file_path=cycle[0],
                start_line=1,
                severity="high",
                perspective=self.name,
                suggestion=(
                    "Extract the shared dependency into a third module that neither "
                    "side of the cycle imports. This breaks the cycle cleanly."
                ),
            ))

        # High fan-out
        for file_rel, mods in sorted(imports.items(), key=lambda x: -len(x[1])):
            if len(mods) >= _HIGH_FAN_OUT:
                findings.append(Finding(
                    title=f"High fan-out: {file_rel} imports {len(mods)} modules",
                    description=(
                        f"`{file_rel}` imports {len(mods)} modules. "
                        "High fan-out increases the blast radius of changes to any "
                        "of those modules."
                    ),
                    file_path=file_rel,
                    start_line=1,
                    severity="medium",
                    perspective=self.name,
                    suggestion=(
                        "Consider grouping related imports behind a facade module, "
                        "or splitting this file into more focused units."
                    ),
                ))

        # High fan-in (approximate: count local imports only)
        local_imported_by = {
            mod: files for mod, files in imported_by.items()
            if not mod.startswith((".", "/"))  # skip stdlib guesses
            and len(files) >= _HIGH_FAN_IN
        }
        for mod, files in sorted(local_imported_by.items(), key=lambda x: -len(x[1]))[:5]:
            findings.append(Finding(
                title=f"High fan-in: '{mod}' imported by {len(files)} files",
                description=(
                    f"Module `{mod}` is imported by {len(files)} files. "
                    "Changes to this module's public API will require updating many call sites."
                ),
                file_path=list(files)[0],
                start_line=1,
                severity="low",
                perspective=self.name,
                suggestion=(
                    "This is not always a problem, but ensure this module has a stable API. "
                    "Consider adding type stubs or a versioned interface."
                ),
            ))

        return findings


# ── Import extraction ──────────────────────────────────────────────────────

_PY_IMPORT  = re.compile(r'^(?:from\s+([\w.]+)\s+import|import\s+([\w., ]+))', re.MULTILINE)
_RS_USE     = re.compile(r'^\s*use\s+([\w:]+)', re.MULTILINE)
_JS_IMPORT = re.compile(
    r'''(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|'''
    r'''require\s*\(\s*['"]([^'"]+)['"]\s*\))''',
    re.MULTILINE,
)


def _extract_imports(src: str, lang: str) -> list[str]:
    mods = []
    if lang == "python":
        for m in _PY_IMPORT.finditer(src):
            mod = (m.group(1) or m.group(2) or "").strip()
            if mod:
                mods.append(mod.split(".")[0])  # top-level module only
    elif lang == "rust":
        for m in _RS_USE.finditer(src):
            mods.append(m.group(1).split("::")[0])
    elif lang in ("javascript", "typescript"):
        for m in _JS_IMPORT.finditer(src):
            mod = (m.group(1) or m.group(2) or "").strip()
            if mod:
                mods.append(mod)
    return mods


# ── Cycle detection ────────────────────────────────────────────────────────

def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Find cycles in a directed graph using DFS. Returns list of cycle paths."""
    visited: set[str] = set()
    path: list[str] = []
    path_set: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        if len(cycles) >= 10:  # early stop
            return
        if node in path_set:
            idx = path.index(node)
            cycles.append(path[idx:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        path.append(node)
        path_set.add(node)
        for neighbour in graph.get(node, set()):
            # Only follow edges within the project (skip stdlib)
            if neighbour in graph:
                dfs(neighbour)
        path.pop()
        path_set.discard(node)

    for node in list(graph.keys()):
        dfs(node)

    return cycles


# ── Helpers ────────────────────────────────────────────────────────────────

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


def _coupling_finding(row: dict, perspective: str) -> Finding:
    return Finding(
        title=f"High coupling: {row.get('file', '?')}",
        description=str(row),
        file_path=row.get("file", ""),
        start_line=0,
        severity="medium",
        perspective=perspective,
        suggestion="Reduce coupling by extracting shared logic into a dedicated module.",
    )


def _summarize(findings: list[Finding]) -> str:
    cycles = sum(1 for f in findings if "Circular" in f.title)
    fan_out = sum(1 for f in findings if "fan-out" in f.title)
    fan_in = sum(1 for f in findings if "fan-in" in f.title)
    parts = []
    if cycles:
        parts.append(f"{cycles} circular import cycle(s)")
    if fan_out:
        parts.append(f"{fan_out} high-fan-out file(s)")
    if fan_in:
        parts.append(f"{fan_in} high-fan-in module(s)")
    return "Dependency analysis: " + (", ".join(parts) or "no issues found") + "."
