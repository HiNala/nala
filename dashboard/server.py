"""
Nala optional web dashboard.

A lightweight FastAPI server on localhost:3000 that visualises the Neo4j
code graph in a browser. Entirely optional — the TUI works without it.

Start with: uvicorn dashboard.server:app --port 3000
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Nala Dashboard",
    description="Code knowledge graph visualisation for Nala",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (index.html, graph.js)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── API routes ─────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    """Serve the dashboard SPA."""
    html_path = static_dir / "index.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>Nala Dashboard</h1><p>Static files not found. Run from project root.</p>"


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": "nala-dashboard", "version": "0.1.0"}


@app.get("/graph")
async def get_graph() -> dict[str, Any]:
    """
    Return the code knowledge graph as JSON nodes and edges.

    Format compatible with D3.js force-directed graphs:
    { "nodes": [...], "links": [...] }
    """
    # Load Neo4j connection using project config
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "python-orchestrator"))
        from nala_orchestrator.config import Config
        from nala_orchestrator.graph.connection import GraphConnection

        config = Config.load()
        conn = GraphConnection(config)
        if not conn.connect():
            return {"nodes": [], "links": [], "error": "Neo4j not available"}

        # Fetch nodes
        file_rows = conn.run("MATCH (f:File) RETURN f.path AS id, 'File' AS type LIMIT 200")
        fn_rows = conn.run(
            "MATCH (fn:Function) RETURN fn.id AS id, fn.name AS label, 'Function' AS type, "
            "fn.cyclomatic AS complexity LIMIT 500"
        )
        rel_rows = conn.run(
            "MATCH (a)-[r]->(b) RETURN a.id AS source, b.id AS target, type(r) AS rel LIMIT 1000"
        )
        conn.close()

        nodes = [{"id": r["id"], "type": r["type"], "label": r.get("label", r["id"])} for r in file_rows + fn_rows]
        links = [{"source": r["source"], "target": r["target"], "rel": r["rel"]} for r in rel_rows]
        return {"nodes": nodes, "links": links}

    except Exception as e:
        return {"nodes": [], "links": [], "error": str(e)}


@app.get("/sessions")
async def list_sessions() -> list[dict]:
    """List all analysis sessions."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "python-orchestrator"))
        from nala_orchestrator.config import Config
        from nala_orchestrator.sessions.manager import SessionManager

        config = Config.load()
        manager = SessionManager(config.project_root)
        sessions = manager.list_sessions()
        return [{"id": s.session_id, "created_at": s.created_at, "status": s.status} for s in sessions]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", "3000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
