"""Graph context provider — extracts LLM-friendly context from the Neo4j graph.

Queries the code knowledge graph for structural insights relevant to
the user's question and formats them as concise context blocks that
can be injected into the system prompt.

Gracefully returns empty strings when Neo4j is unavailable.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import GraphConnection

log = logging.getLogger(__name__)

_MAX_ITEMS = 12


class GraphContextProvider:
    """Extracts structured context from the code knowledge graph."""

    def __init__(self, conn: GraphConnection) -> None:
        self._conn = conn

    def is_available(self) -> bool:
        return self._conn.is_available()

    # ── High-level API ────────────────────────────────────────────────

    def context_for_query(self, query: str, max_chars: int = 3000) -> str:
        """Build a context block relevant to a natural-language query.

        Extracts file names and function/class names from the query text,
        then fetches structural relationships from the graph.
        """
        if not self._conn.is_available():
            return ""

        parts: list[str] = []
        total = 0

        file_hints = _extract_file_hints(query)
        symbol_hints = _extract_symbol_hints(query)

        if file_hints:
            for fpath in file_hints[:3]:
                section = self._file_relationships(fpath)
                if section and total + len(section) < max_chars:
                    parts.append(section)
                    total += len(section)

        if symbol_hints:
            for sym in symbol_hints[:4]:
                section = self._symbol_context(sym)
                if section and total + len(section) < max_chars:
                    parts.append(section)
                    total += len(section)

        if not parts:
            section = self._project_overview()
            if section:
                parts.append(section)

        if not parts:
            return ""

        return "[CODE GRAPH CONTEXT]\n" + "\n\n".join(parts) + "\n[END GRAPH CONTEXT]"

    def context_for_planning(self, objective: str, max_chars: int = 4000) -> str:
        """Build a structural overview for agent mission planning."""
        if not self._conn.is_available():
            return ""

        parts: list[str] = []
        total = 0

        overview = self._project_overview()
        if overview:
            parts.append(overview)
            total += len(overview)

        hotspots = self._complexity_hotspots()
        if hotspots and total + len(hotspots) < max_chars:
            parts.append(hotspots)
            total += len(hotspots)

        coupling = self._high_coupling()
        if coupling and total + len(coupling) < max_chars:
            parts.append(coupling)
            total += len(coupling)

        file_hints = _extract_file_hints(objective)
        for fpath in file_hints[:3]:
            section = self._file_relationships(fpath)
            if section and total + len(section) < max_chars:
                parts.append(section)
                total += len(section)

        if not parts:
            return ""

        return "[CODE GRAPH STRUCTURE]\n" + "\n\n".join(parts) + "\n[END GRAPH STRUCTURE]"

    # ── Internal query helpers ────────────────────────────────────────

    def _project_overview(self) -> str:
        """Summary counts: files, functions, classes, modules."""
        try:
            rows = self._conn.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
            )
            if not rows:
                return ""
            counts = {r["label"]: r["cnt"] for r in rows if r.get("label")}
            if not counts:
                return ""
            lines = ["### Graph Overview"]
            for label in ("File", "Function", "Class", "Module"):
                if label in counts:
                    lines.append(f"- {label}s: {counts[label]}")
            return "\n".join(lines)
        except Exception as exc:
            log.debug("Graph overview failed: %s", exc)
            return ""

    def _file_relationships(self, file_path: str) -> str:
        """What does this file import and what imports it?"""
        try:
            imports = self._conn.run(
                "MATCH (f:File {path: $path})-[:IMPORTS]->(m) "
                "RETURN m.name AS module LIMIT $lim",
                path=file_path, lim=_MAX_ITEMS,
            )
            imported_by = self._conn.run(
                "MATCH (f:File)-[:IMPORTS]->(t:File {path: $path}) "
                "RETURN f.path AS file LIMIT $lim",
                path=file_path, lim=_MAX_ITEMS,
            )
            functions = self._conn.run(
                "MATCH (f:File {path: $path})-[:CONTAINS]->(fn:Function) "
                "RETURN fn.name AS name, fn.cyclomatic AS complexity "
                "ORDER BY fn.cyclomatic DESC LIMIT $lim",
                path=file_path, lim=_MAX_ITEMS,
            )
            if not imports and not imported_by and not functions:
                return ""

            lines = [f"### {file_path}"]
            if imports:
                lines.append("Imports: " + ", ".join(r["module"] for r in imports))
            if imported_by:
                lines.append("Imported by: " + ", ".join(r["file"] for r in imported_by))
            if functions:
                fn_strs = []
                for r in functions:
                    cx = f" (complexity: {r['complexity']})" if r.get("complexity") else ""
                    fn_strs.append(f"{r['name']}{cx}")
                lines.append("Functions: " + ", ".join(fn_strs))
            return "\n".join(lines)
        except Exception as exc:
            log.debug("File relationships failed for %s: %s", file_path, exc)
            return ""

    def _symbol_context(self, symbol_name: str) -> str:
        """Get callers and callees for a function/class name."""
        try:
            callers = self._conn.run(
                "MATCH (caller:Function)-[:CALLS]->(fn:Function {name: $name}) "
                "RETURN caller.name AS name, caller.file_path AS file LIMIT $lim",
                name=symbol_name, lim=_MAX_ITEMS,
            )
            callees = self._conn.run(
                "MATCH (fn:Function {name: $name})-[:CALLS]->(callee:Function) "
                "RETURN callee.name AS name, callee.file_path AS file LIMIT $lim",
                name=symbol_name, lim=_MAX_ITEMS,
            )
            info = self._conn.run(
                "MATCH (fn:Function {name: $name}) "
                "RETURN fn.file_path AS file, fn.start_line AS line, "
                "fn.cyclomatic AS complexity LIMIT 1",
                name=symbol_name,
            )
            if not callers and not callees and not info:
                return ""

            lines = [f"### `{symbol_name}`"]
            if info:
                r = info[0]
                loc = f"Defined in {r.get('file', '?')}"
                if r.get("line"):
                    loc += f":{r['line']}"
                if r.get("complexity"):
                    loc += f" (complexity: {r['complexity']})"
                lines.append(loc)
            if callers:
                lines.append("Called by: " + ", ".join(
                    f"{r['name']} ({r['file']})" for r in callers
                ))
            if callees:
                lines.append("Calls: " + ", ".join(
                    f"{r['name']} ({r['file']})" for r in callees
                ))
            return "\n".join(lines)
        except Exception as exc:
            log.debug("Symbol context failed for %s: %s", symbol_name, exc)
            return ""

    def _complexity_hotspots(self, threshold: int = 10) -> str:
        """Functions with high cyclomatic complexity."""
        try:
            rows = self._conn.run(
                "MATCH (fn:Function) WHERE fn.cyclomatic >= $t "
                "RETURN fn.name AS name, fn.file_path AS file, fn.cyclomatic AS cx "
                "ORDER BY fn.cyclomatic DESC LIMIT $lim",
                t=threshold, lim=8,
            )
            if not rows:
                return ""
            lines = ["### Complexity Hotspots"]
            for r in rows:
                lines.append(f"- {r['name']} ({r['file']}) — complexity: {r['cx']}")
            return "\n".join(lines)
        except Exception as exc:
            log.debug("Complexity hotspots failed: %s", exc)
            return ""

    def _high_coupling(self) -> str:
        """Files with high fan-out (many imports)."""
        try:
            rows = self._conn.run(
                "MATCH (f:File)-[:IMPORTS]->(m) "
                "WITH f, count(m) AS out_count WHERE out_count >= 10 "
                "RETURN f.path AS file, out_count ORDER BY out_count DESC LIMIT 5",
            )
            if not rows:
                return ""
            lines = ["### High Coupling"]
            for r in rows:
                lines.append(f"- {r['file']} — {r['out_count']} imports")
            return "\n".join(lines)
        except Exception as exc:
            log.debug("High coupling failed: %s", exc)
            return ""


# ── Text extraction helpers ──────────────────────────────────────────

_FILE_PATTERN = re.compile(
    r'[\w./\\-]+\.(?:py|rs|ts|tsx|js|jsx|go|java|c|cpp|h|hpp|rb|toml|yaml|yml|json|md)'
)
_SYMBOL_PATTERN = re.compile(r'\b([A-Z][a-zA-Z0-9]+|[a-z_][a-z0-9_]{2,})\b')

_COMMON_WORDS = frozenset({
    "the", "and", "for", "with", "this", "that", "from", "what", "how",
    "why", "when", "where", "which", "does", "not", "are", "was", "been",
    "can", "will", "should", "would", "could", "have", "has", "had",
    "all", "any", "some", "into", "out", "about", "just", "make",
    "use", "get", "set", "add", "new", "file", "code", "function",
    "class", "method", "module", "import", "return", "error", "test",
    "def", "var", "let", "const", "async", "await", "true", "false",
    "none", "self", "cls", "type", "list", "dict", "str", "int",
})


def _extract_file_hints(text: str) -> list[str]:
    """Extract file paths mentioned in the text."""
    return _FILE_PATTERN.findall(text)


def _extract_symbol_hints(text: str) -> list[str]:
    """Extract plausible function/class names from the text."""
    candidates = _SYMBOL_PATTERN.findall(text)
    return [
        c for c in candidates
        if c.lower() not in _COMMON_WORDS and len(c) > 2
    ][:8]
