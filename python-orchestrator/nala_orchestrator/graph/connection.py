"""
Neo4j connection manager.

Handles connecting, health checking, and gracefully degrading when Neo4j
is not available. The graph is optional — Nala works without it, but
dependency analysis and graph-based perspectives require it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nala_orchestrator.config import Config


class GraphConnection:
    """Manages the Neo4j driver connection."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._driver = None
        self._available = False

    def connect(self) -> bool:
        """Attempt to connect to Neo4j. Returns True if successful."""
        if not self.config.neo4j_enabled:
            return False
        if not self.config.neo4j_password:
            return False

        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                self.config.neo4j_uri,
                auth=(self.config.neo4j_user, self.config.neo4j_password),
            )
            self._driver.verify_connectivity()
            self._available = True
            return True
        except Exception as e:
            self._available = False
            self._driver = None
            import logging
            logging.getLogger(__name__).warning(
                "Neo4j not available: %s. Graph features disabled.", e
            )
            return False

    def is_available(self) -> bool:
        return self._available

    def run(self, cypher: str, **params: Any) -> list[dict]:
        """Execute a Cypher query and return rows as dicts."""
        if not self._driver or not self._available:
            return []
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            return [dict(record) for record in result]

    def run_write(self, cypher: str, **params: Any) -> None:
        """Execute a write Cypher query."""
        if not self._driver or not self._available:
            return
        with self._driver.session() as session:
            session.run(cypher, **params)

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None
            self._available = False

    def __enter__(self) -> GraphConnection:
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
