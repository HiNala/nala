"""
Dead code perspective.

Finds functions and classes that are defined but never referenced anywhere
in the project. Works in two modes:

  Graph mode (requires Neo4j): queries CALLS and IMPORTS relationships for
  zero-incoming-edge nodes. Accurate.

  Heuristic mode (no Neo4j): scans all source files for definition patterns,
  then checks whether each defined name appears anywhere else in the codebase.
  Fast and good enough for private/internal symbols.

The heuristic deliberately excludes:
  - Public API symbols (exported, pub, non-underscore-prefixed in Python)
  - Entry points: main(), __init__, setUp, tearDown, test_*
  - Dunder methods (__str__, __repr__, etc.)
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

# Names that are never dead code regardless of call count
_ALWAYS_LIVE = re.compile(
    r"^(main|__init__|__new__|__del__|__repr__|__str__|__len__|__iter__|"
    r"__next__|__enter__|__exit__|__call__|__getitem__|__setitem__|"
    r"setUp|tearDown|setUpClass|tearDownClass|test_|spec_|describe_|"
    r"beforeEach|afterEach|beforeAll|afterAll)$"
)


class DeadCodePerspective(BasePerspective):
    """Finds functions and classes defined but never referenced."""

    @property
    def name(self) -> str:
        return "dead_code"

    @property
    def description(self) -> str:
        return "Finds functions and classes that are defined but never referenced"

    def requires_graph(self) -> bool:
        return False  # We have a heuristic fallback

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
            summary=(
                f"Found {len(findings)} potentially dead symbols "
                f"(private/internal, never referenced outside their file)."
            ),
            duration_ms=duration_ms,
        )

    # ── Graph mode ─────────────────────────────────────────────────────────

    async def _analyze_via_graph(self) -> list[Finding]:
        from ..graph.queries import find_isolated_functions
        cypher, params = find_isolated_functions()
        rows = self.graph.run(cypher, **params)
        findings = []
        for row in rows:
            name = row.get("name", "?")
            if _ALWAYS_LIVE.match(name):
                continue
            findings.append(Finding(
                title=f"Dead function: {name}",
                description=(
                    f"`{name}` has no incoming CALLS relationships in the code graph. "
                    "It may be unused code that can be safely removed."
                ),
                file_path=row.get("file_path", "unknown"),
                start_line=row.get("start_line", 0),
                severity="low",
                perspective=self.name,
                suggestion=(
                    "Verify this function is not called via dynamic dispatch or "
                    "reflection, then remove if unused."
                ),
            ))
        return findings

    # ── Heuristic mode ─────────────────────────────────────────────────────

    def _analyze_heuristic(self, project_root: str) -> list[Finding]:
        root = Path(project_root)
        source_files = list(_iter_source_files(root))

        # Phase 1: collect definitions per file
        definitions: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
        for path in source_files:
            rel = str(path.relative_to(root))
            lang = _detect_lang(path.suffix)
            try:
                src = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name, lineno, visibility in _extract_definitions(src, lang):
                definitions[name].append((rel, lineno, visibility))

        # Phase 2: build a reference corpus (all text from all files)
        # We do a single pass collecting all identifiers to avoid O(n*m) scanning
        all_refs: set[str] = set()
        for path in source_files:
            try:
                src = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Simple word extraction — fast and good enough
            all_refs.update(re.findall(r'\b[a-zA-Z_]\w*\b', src))

        # Phase 3: cross-reference
        findings: list[Finding] = []
        for name, locations in definitions.items():
            # Skip always-live names
            if _ALWAYS_LIVE.match(name):
                continue
            # Skip names with multiple definition sites (interface implementations)
            if len(locations) > 1:
                continue
            rel, lineno, visibility = locations[0]
            # Only flag private/internal symbols
            if visibility == "public":
                continue
            # The name appears in all_refs (it's always there from its definition)
            # but if it appears only once it means only the definition site
            # Count occurrences across all file text
            total_refs = sum(
                len(re.findall(r'\b' + re.escape(name) + r'\b',
                               _read_file_cached(root / r, _file_cache := {})))
                for r, _, _ in [(rel, lineno, visibility)]
            )
            # If only 1 occurrence that's just the definition
            if total_refs <= 1:
                findings.append(Finding(
                    title=f"Possibly unused: {name}",
                    description=(
                        f"`{name}` is a private symbol defined in `{rel}:{lineno}` "
                        "that appears to have no callers. It may be dead code."
                    ),
                    file_path=rel,
                    start_line=lineno,
                    severity="low",
                    perspective=self.name,
                    suggestion=(
                        "Search for all usages with your IDE, then remove if truly unused. "
                        "Beware of dynamic dispatch (getattr, reflection, decorators)."
                    ),
                ))

        return findings[:50]  # Cap at 50 to avoid flooding findings


# ── Extraction helpers ─────────────────────────────────────────────────────

_PY_FUNC_DEF = re.compile(
    r'^(?P<indent>\s*)(?P<pub>)def\s+(?P<name>_?\w+)\s*\(',
    re.MULTILINE,
)
_PY_CLASS_DEF = re.compile(
    r'^(?P<indent>\s*)class\s+(?P<name>_?\w+)\s*[:(]',
    re.MULTILINE,
)
_RS_FN_DEF = re.compile(
    r'^\s*(?P<pub>pub\s+)?(?:async\s+)?fn\s+(?P<name>\w+)\s*[<(]',
    re.MULTILINE,
)
_RS_STRUCT_DEF = re.compile(
    r'^\s*(?P<pub>pub\s+)?struct\s+(?P<name>\w+)',
    re.MULTILINE,
)
_JS_FUNC_DEF = re.compile(
    r'(?:function\s+(?P<name>\w+)|'
    r'(?:const|let|var)\s+(?P<name2>\w+)\s*=\s*(?:async\s*)?\()',
    re.MULTILINE,
)


def _extract_definitions(src: str, lang: str) -> list[tuple[str, int, str]]:
    """Return [(name, lineno, visibility)] for definitions in src."""
    results = []
    lines = src.splitlines()

    if lang == "python":
        for m in _PY_FUNC_DEF.finditer(src):
            name = m.group("name")
            lineno = src[:m.start()].count("\n") + 1
            vis = "private" if name.startswith("_") else "public"
            results.append((name, lineno, vis))
        for m in _PY_CLASS_DEF.finditer(src):
            name = m.group("name")
            lineno = src[:m.start()].count("\n") + 1
            vis = "private" if name.startswith("_") else "public"
            results.append((name, lineno, vis))

    elif lang == "rust":
        for m in _RS_FN_DEF.finditer(src):
            name = m.group("name")
            lineno = src[:m.start()].count("\n") + 1
            vis = "public" if m.group("pub") else "private"
            results.append((name, lineno, vis))
        for m in _RS_STRUCT_DEF.finditer(src):
            name = m.group("name")
            lineno = src[:m.start()].count("\n") + 1
            vis = "public" if m.group("pub") else "private"
            results.append((name, lineno, vis))

    elif lang in ("javascript", "typescript"):
        for m in _JS_FUNC_DEF.finditer(src):
            name = m.group("name") or m.group("name2")
            if not name:
                continue
            lineno = src[:m.start()].count("\n") + 1
            # JS: treat exported as public
            line_text = lines[lineno - 1] if lineno <= len(lines) else ""
            vis = "public" if "export" in line_text else "private"
            results.append((name, lineno, vis))

    return results


_file_cache: dict[Path, str] = {}

def _read_file_cached(path: Path, cache: dict) -> str:
    if path not in _file_cache:
        try:
            _file_cache[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            _file_cache[path] = ""
    return _file_cache[path]


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
