"""
Nala optional web dashboard — FastAPI backend.

Binds to 127.0.0.1 only. CORS is restricted to localhost origins.
Start with: python -m dashboard.server  or  nala dashboard

Endpoints:
  GET /            — dashboard SPA (index.html)
  GET /health      — health check
  GET /graph       — code graph as D3-compatible {nodes, links, stats}
  GET /complexity  — functions above complexity threshold
  GET /findings    — findings from latest (or specified) session
  GET /files       — file list with language, size, symbol count
  GET /sessions    — list all analysis sessions
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Make the orchestrator importable when running from repo root
_repo_root = Path(__file__).resolve().parent.parent
_orch_path = str(_repo_root / "python-orchestrator")
if _orch_path not in sys.path:
    sys.path.insert(0, _orch_path)

app = FastAPI(
    title="Nala Dashboard",
    description="Code knowledge graph visualisation for Nala",
    version="0.1.0",
)

# CORS — localhost only (never 0.0.0.0)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

_default_project_root = os.environ.get("NALA_PROJECT_ROOT", ".")


# ── Internal helpers ────────────────────────────────────────────────────────

def _load_config(project_root: str = "."):
    from nala_orchestrator.config import Config
    return Config.load(project_root=Path(project_root).resolve())


def _graph_connection(config):
    try:
        from nala_orchestrator.graph.connection import GraphConnection
        conn = GraphConnection(config)
        return conn if conn.connect() else None
    except Exception:
        return None


def _cache_db(project_root: str) -> Optional[sqlite3.Connection]:
    db_path = Path(project_root).resolve() / ".nala" / "cache.db"
    if not db_path.exists():
        return None
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _latest_findings(project_root: str) -> list[dict]:
    try:
        from nala_orchestrator.sessions.manager import SessionManager
        sm = SessionManager(Path(project_root).resolve())
        sessions = sm.list_sessions()
        if not sessions:
            return []
        sm.load_session(sessions[0].session_id)
        return sm.load_findings_raw()
    except Exception:
        return []


def _severity_rank(s: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(s, 9)


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    html = _static_dir / "index.html"
    if html.exists():
        return html.read_text(encoding="utf-8")
    return "<h1>Nala Dashboard</h1><p>Static files not found.</p>"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "nala-dashboard", "version": "0.1.0"}


@app.get("/graph")
async def get_graph(
    project_root: str = Query(_default_project_root, description="Project root directory"),
    max_nodes: int = Query(300, ge=10, le=2000),
) -> dict[str, Any]:
    """Code graph as D3-compatible {nodes, links, stats}. Falls back to cache."""
    try:
        config = _load_config(project_root)
        conn = _graph_connection(config)
        nodes: list[dict] = []
        links: list[dict] = []

        if conn:
            file_rows = conn.run(
                "MATCH (f:File) RETURN f.path AS id, 'File' AS type, "
                "f.path AS label, coalesce(f.sloc,0) AS sloc LIMIT $lim",
                {"lim": max_nodes // 2},
            )
            fn_rows = conn.run(
                "MATCH (fn:Function) RETURN fn.id AS id, fn.name AS label, "
                "'Function' AS type, coalesce(fn.cyclomatic,0) AS complexity LIMIT $lim",
                {"lim": max_nodes // 2},
            )
            rel_rows = conn.run(
                "MATCH (a)-[r]->(b) WHERE a.id IS NOT NULL AND b.id IS NOT NULL "
                "RETURN a.id AS source, b.id AS target, type(r) AS rel LIMIT 2000"
            )
            conn.close()
            for r in file_rows + fn_rows:
                nodes.append({
                    "id": r.get("id", ""),
                    "type": r.get("type", "File"),
                    "label": (r.get("label") or r.get("id") or "").split("/")[-1],
                    "complexity": r.get("complexity", 0),
                    "sloc": r.get("sloc", 0),
                })
            links = [
                {"source": r["source"], "target": r["target"], "rel": r.get("rel", "")}
                for r in rel_rows if r.get("source") and r.get("target")
            ]
        else:
            # Fallback: files from SQLite cache
            con = _cache_db(project_root)
            if con:
                rows = con.execute(
                    "SELECT relative_path, language, symbol_count FROM file_index "
                    "ORDER BY symbol_count DESC LIMIT ?", (max_nodes,)
                ).fetchall()
                con.close()
                for r in rows:
                    nodes.append({
                        "id": r["relative_path"],
                        "type": "File",
                        "label": r["relative_path"].split("/")[-1],
                        "complexity": 0,
                        "sloc": 0,
                        "language": r["language"] or "?",
                    })

        lang_counts: dict[str, int] = {}
        for n in nodes:
            if n["type"] == "File":
                ext = n["id"].rsplit(".", 1)[-1] if "." in n["id"] else "?"
                lang_counts[ext] = lang_counts.get(ext, 0) + 1

        return {
            "nodes": nodes,
            "links": links,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(links),
                "languages": lang_counts,
            },
        }
    except Exception as exc:
        return {"nodes": [], "links": [], "stats": {}, "error": str(exc)}


@app.get("/complexity")
async def get_complexity(
    project_root: str = Query(_default_project_root),
    threshold: int = Query(5, ge=1),
    limit: int = Query(100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """Functions with cyclomatic complexity >= threshold, sorted descending."""
    try:
        config = _load_config(project_root)
        conn = _graph_connection(config)
        if conn:
            rows = conn.run(
                "MATCH (fn:Function) WHERE coalesce(fn.cyclomatic,0) >= $t "
                "RETURN fn.name AS name, fn.file_path AS file, "
                "fn.start_line AS line, fn.cyclomatic AS cc, fn.cognitive AS cog "
                "ORDER BY fn.cyclomatic DESC LIMIT $lim",
                {"t": threshold, "lim": limit},
            )
            conn.close()
            return [
                {
                    "name": r.get("name", ""),
                    "file": r.get("file", ""),
                    "line": r.get("line") or 0,
                    "cyclomatic": r.get("cc") or 0,
                    "cognitive": r.get("cog") or 0,
                }
                for r in rows
            ]

        # Fallback: complexity findings from latest session
        results = []
        for pdata in _latest_findings(project_root):
            if pdata.get("perspective_name") != "complexity":
                continue
            for f in pdata.get("findings", []):
                meta = f.get("metadata", {}) or {}
                cc = meta.get("cyclomatic_complexity", 0)
                if cc >= threshold:
                    results.append({
                        "name": f.get("title", ""),
                        "file": f.get("file_path", ""),
                        "line": f.get("start_line", 0),
                        "cyclomatic": cc,
                        "cognitive": meta.get("cognitive_complexity", 0),
                    })
        results.sort(key=lambda x: x["cyclomatic"], reverse=True)
        return results[:limit]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/findings")
async def get_findings(
    project_root: str = Query(_default_project_root),
    session_id: Optional[str] = Query(None),
) -> list[dict[str, Any]]:
    """Findings from the latest (or specified) session, sorted by severity."""
    try:
        from nala_orchestrator.sessions.manager import SessionManager
        sm = SessionManager(Path(project_root).resolve())
        sessions = sm.list_sessions()
        if not sessions:
            return []

        target = session_id if (session_id and session_id != "latest") else sessions[0].session_id
        if sm.load_session(target) is None:
            raise HTTPException(status_code=404, detail=f"Session {target!r} not found")

        results: list[dict[str, Any]] = []
        for pdata in sm.load_findings_raw():
            p_name = pdata.get("perspective_name", "unknown")
            for f in pdata.get("findings", []):
                results.append({
                    "perspective": p_name,
                    "severity": f.get("severity", "info"),
                    "title": f.get("title", ""),
                    "file": f.get("file_path", ""),
                    "line": f.get("start_line", 0),
                    "message": f.get("message", ""),
                    "recommendation": f.get("recommendation", ""),
                })
        results.sort(key=lambda x: _severity_rank(x["severity"]))
        return results
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/files")
async def get_files(
    project_root: str = Query(_default_project_root),
    limit: int = Query(500, ge=1, le=5000),
) -> list[dict[str, Any]]:
    """File list from SQLite cache, ordered by symbol count desc."""
    try:
        con = _cache_db(project_root)
        if con is None:
            return []
        rows = con.execute(
            "SELECT relative_path, language, size_bytes, symbol_count "
            "FROM file_index ORDER BY symbol_count DESC LIMIT ?",
            (limit,),
        ).fetchall()
        con.close()
        return [
            {
                "path": r["relative_path"],
                "language": r["language"] or "unknown",
                "size_bytes": r["size_bytes"] or 0,
                "symbol_count": r["symbol_count"] or 0,
            }
            for r in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/sessions")
async def list_sessions(
    project_root: str = Query(_default_project_root),
) -> list[dict[str, Any]]:
    """List all analysis sessions for the project."""
    try:
        from nala_orchestrator.sessions.manager import SessionManager
        sm = SessionManager(Path(project_root).resolve())
        return [
            {
                "id": s.session_id,
                "created_at": s.created_at,
                "status": s.status,
                "total_turns": s.total_turns,
                "perspectives_run": s.perspectives_run,
            }
            for s in sm.list_sessions()
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", "3000"))
    print(f"Nala dashboard starting on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
