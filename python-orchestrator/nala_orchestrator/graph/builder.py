"""
Graph builder — populates the Neo4j graph from Rust indexer output.

Takes the JSON output from nala_core.index_project() and creates nodes
and relationships in Neo4j using batch UNWIND queries for performance.
Runs after every indexing cycle.

If Neo4j is not available, this module is a no-op. All downstream code
checks GraphConnection.is_available() before attempting graph queries.

Performance target: 10,000 symbols in under 10 seconds.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from .connection import GraphConnection
from .schema import SCHEMA_CYPHER

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Batch size for UNWIND queries — keeps individual transactions manageable.
_BATCH_SIZE = 500


class GraphBuilder:
    """Populates the code knowledge graph from index data."""

    def __init__(self, connection: GraphConnection) -> None:
        self.conn = connection

    def ensure_schema(self) -> None:
        """Create constraints and indexes if they do not exist."""
        if not self.conn.is_available():
            return
        for statement in SCHEMA_CYPHER.strip().split(";"):
            s = statement.strip()
            if s:
                try:
                    self.conn.run_write(s)
                except Exception as e:
                    logger.debug("Schema statement skipped: %s", e)

    def populate_from_index(self, index_json: str) -> int:
        """
        Populate the graph from nala_core.index_project() JSON output.

        Returns the total number of nodes created or updated.
        """
        if not self.conn.is_available():
            return 0

        try:
            data = json.loads(index_json)
        except json.JSONDecodeError as e:
            logger.error("Invalid index JSON: %s", e)
            return 0

        symbols: list[dict] = data.get("symbols", [])
        if not symbols:
            logger.debug("No symbols in index data; graph not updated.")
            return 0

        # Group symbols by kind for targeted batch queries.
        functions:  list[dict] = []
        classes:    list[dict] = []
        imports:    list[dict] = []
        calls:      list[dict] = []
        file_paths: set[str] = set()

        for sym in symbols:
            file_paths.add(sym.get("file_path", ""))
            kind = sym.get("kind", "")
            if kind == "function":
                functions.append(sym)
            elif kind in ("class", "struct", "enum"):
                classes.append(sym)
            elif kind == "import":
                imports.append(sym)
            elif kind == "call":
                calls.append(sym)

        total = 0
        total += self._upsert_files(list(file_paths))
        total += self._upsert_functions(functions)
        total += self._upsert_classes(classes)
        total += self._upsert_imports(imports)
        total += self._upsert_calls(calls)

        logger.info(
            "Graph builder: %d files, %d functions, %d classes, %d imports, %d calls",
            len(file_paths), len(functions), len(classes), len(imports), len(calls),
        )
        return total

    def populate_file(self, path: str, language: str, size_bytes: int) -> None:
        """Upsert a single File node."""
        if not self.conn.is_available():
            return
        self.conn.run_write(
            "MERGE (f:File {path: $path}) SET f.language=$lang, f.size_bytes=$sz",
            path=path, lang=language, sz=size_bytes,
        )

    # ── Internal batch helpers ────────────────────────────────────────────────

    def _upsert_files(self, paths: list[str]) -> int:
        """Ensure a File node exists for every file path."""
        for i in range(0, len(paths), _BATCH_SIZE):
            batch = [{"path": p} for p in paths[i:i + _BATCH_SIZE]]
            self.conn.run_write(
                """
                UNWIND $rows AS row
                MERGE (f:File {path: row.path})
                """,
                rows=batch,
            )
        return len(paths)

    def _upsert_functions(self, symbols: list[dict]) -> int:
        """Batch upsert Function nodes and CONTAINS relationships."""
        for i in range(0, len(symbols), _BATCH_SIZE):
            batch = [
                {
                    "id":         f"{s['file_path']}:{s['name']}:{s['start_line']}",
                    "name":       s["name"],
                    "file_path":  s["file_path"],
                    "start_line": s.get("start_line", 0),
                    "end_line":   s.get("end_line", 0),
                    "language":   s.get("language", ""),
                    "visibility": s.get("metadata", {}).get("visibility", ""),
                    "cyclomatic": int(s.get("metadata", {}).get("cyclomatic", 0) or 0),
                }
                for s in symbols[i:i + _BATCH_SIZE]
            ]
            self.conn.run_write(
                """
                UNWIND $rows AS row
                MERGE (fn:Function {id: row.id})
                SET fn.name       = row.name,
                    fn.file_path  = row.file_path,
                    fn.start_line = row.start_line,
                    fn.end_line   = row.end_line,
                    fn.language   = row.language,
                    fn.visibility = row.visibility,
                    fn.cyclomatic = row.cyclomatic
                WITH fn, row
                MATCH (f:File {path: row.file_path})
                MERGE (f)-[:CONTAINS]->(fn)
                """,
                rows=batch,
            )
        return len(symbols)

    def _upsert_classes(self, symbols: list[dict]) -> int:
        """Batch upsert Class nodes and CONTAINS relationships."""
        for i in range(0, len(symbols), _BATCH_SIZE):
            batch = [
                {
                    "id":         f"{s['file_path']}:{s['name']}:{s['start_line']}",
                    "name":       s["name"],
                    "file_path":  s["file_path"],
                    "start_line": s.get("start_line", 0),
                    "end_line":   s.get("end_line", 0),
                    "language":   s.get("language", ""),
                    "kind":       s.get("kind", "class"),
                }
                for s in symbols[i:i + _BATCH_SIZE]
            ]
            self.conn.run_write(
                """
                UNWIND $rows AS row
                MERGE (c:Class {id: row.id})
                SET c.name       = row.name,
                    c.file_path  = row.file_path,
                    c.start_line = row.start_line,
                    c.end_line   = row.end_line,
                    c.language   = row.language,
                    c.kind       = row.kind
                WITH c, row
                MATCH (f:File {path: row.file_path})
                MERGE (f)-[:CONTAINS]->(c)
                """,
                rows=batch,
            )
        return len(symbols)

    def _upsert_calls(self, symbols: list[dict]) -> int:
        """Batch upsert CALLS relationships between functions.

        Each call symbol has a name (the callee) and exists inside a file at a
        line. We match the caller function as the one in the same file whose
        line range encloses the call site, then create a CALLS edge to any
        function node with the same name.
        """
        for i in range(0, len(symbols), _BATCH_SIZE):
            batch = [
                {
                    "file_path":  s["file_path"],
                    "callee":     s["name"],
                    "call_line":  s.get("start_line", 0),
                }
                for s in symbols[i:i + _BATCH_SIZE]
            ]
            self.conn.run_write(
                """
                UNWIND $rows AS row
                OPTIONAL MATCH (caller:Function)
                WHERE caller.file_path = row.file_path
                  AND caller.start_line <= row.call_line
                  AND caller.end_line >= row.call_line
                WITH caller, row
                WHERE caller IS NOT NULL
                OPTIONAL MATCH (callee:Function)
                WHERE callee.name = row.callee
                WITH caller, callee, row
                WHERE callee IS NOT NULL
                MERGE (caller)-[:CALLS {line: row.call_line}]->(callee)
                """,
                rows=batch,
            )
        return len(symbols)

    def _upsert_imports(self, symbols: list[dict]) -> int:
        """Batch upsert IMPORTS relationships from File to Module."""
        for i in range(0, len(symbols), _BATCH_SIZE):
            batch = [
                {
                    "file_path":    s["file_path"],
                    "module_name":  s["name"],
                    "imported_as":  s.get("metadata", {}).get("alias", s["name"]),
                }
                for s in symbols[i:i + _BATCH_SIZE]
            ]
            self.conn.run_write(
                """
                UNWIND $rows AS row
                MATCH (f:File {path: row.file_path})
                MERGE (m:Module {name: row.module_name})
                MERGE (f)-[:IMPORTS {imported_as: row.imported_as}]->(m)
                """,
                rows=batch,
            )
        return len(symbols)
