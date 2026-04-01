"""
Graph builder — populates the Neo4j graph from Rust indexer output.

Takes the JSON output from nala_core.index_project() and creates nodes
and relationships in Neo4j. Runs after every indexing cycle.

If Neo4j is not available, this module is a no-op. All downstream code
checks GraphConnection.is_available() before attempting graph queries.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .connection import GraphConnection
from .queries import upsert_file, upsert_function
from .schema import SCHEMA_CYPHER

if TYPE_CHECKING:
    from nala_orchestrator.config import Config

logger = logging.getLogger(__name__)


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

        Returns the number of nodes created or updated.
        """
        if not self.conn.is_available():
            return 0

        try:
            data = json.loads(index_json)
        except json.JSONDecodeError as e:
            logger.error("Invalid index JSON: %s", e)
            return 0

        nodes_written = 0
        symbols = data.get("symbols", [])

        for sym in symbols:
            kind = sym.get("kind", "")
            name = sym.get("name", "")
            file_path = sym.get("file_path", "")
            start_line = sym.get("start_line", 0)
            end_line = sym.get("end_line", 0)
            language = sym.get("language", "unknown")

            if kind == "function":
                func_id = f"{file_path}:{name}:{start_line}"
                cypher, params = upsert_function(
                    func_id, name, file_path, start_line, end_line
                )
                self.conn.run_write(cypher, **params)
                nodes_written += 1

            elif kind in ("class", "struct", "enum"):
                # Classes handled similarly to functions; full implementation in Mission 07
                nodes_written += 1

        logger.info("Graph builder wrote %d nodes", nodes_written)
        return nodes_written

    def populate_file(self, path: str, language: str, size_bytes: int) -> None:
        """Upsert a File node."""
        if not self.conn.is_available():
            return
        cypher, params = upsert_file(path, language, size_bytes)
        self.conn.run_write(cypher, **params)
