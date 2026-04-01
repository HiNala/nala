"""
nala_orchestrator — Python orchestration layer for Nala.

Coordinates AI providers, Neo4j code graph, analysis perspectives,
session management, and mission generation. Works in tandem with the
Rust core (nala_core) which handles fast file scanning and parsing.

Typical usage:
    from nala_orchestrator.config import Config
    from nala_orchestrator.agents.orchestrator import AgentOrchestrator

    config = Config.load()
    agent = AgentOrchestrator(config)
    response = await agent.query("What are the most complex functions?")
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
