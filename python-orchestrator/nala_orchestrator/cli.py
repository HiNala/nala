"""
Nala Python IPC server.

Spawned by the Rust TUI as a subprocess. Reads JSON-lines requests from
stdin and writes JSON-lines responses to stdout.

Full protocol (JSON-lines over stdin/stdout):

  ── LLM ───────────────────────────────────────────────────────────────────
  Request:  {"id":"1","type":"query","text":"..."}
  Response: {"id":"1","type":"chunk","text":"..."}   (0..N)
            {"id":"1","type":"done"}
            {"id":"1","type":"error","text":"..."}

  ── Analysis ──────────────────────────────────────────────────────────────
  Request:  {"id":"2","type":"run_perspectives","perspective":"all"}
  Response: (same chunk/done/error pattern as query)

  ── Sessions ──────────────────────────────────────────────────────────────
  Request:  {"id":"3","type":"list_sessions"}
  Response: {"id":"3","type":"sessions","sessions":[...]}

  Request:  {"id":"4","type":"new_session"}
  Response: {"id":"4","type":"session_created","session_id":"...","summary":"..."}

  Request:  {"id":"5","type":"load_session","session_id":"20250101_120000"}
  Response: {"id":"5","type":"session_loaded","session_id":"...","turn_count":12}

  Request:  {"id":"6","type":"session_summary"}
  Response: {"id":"6","type":"session_summary","text":"..."}

  ── Mission generation ────────────────────────────────────────────────────
  Request:  {"id":"7","type":"generate_mission","focus":""}
  Response: (same chunk/done/error pattern — streams the markdown)

  ── Housekeeping ──────────────────────────────────────────────────────────
  Request:  {"id":"8","type":"index_context","total_files":10,"total_symbols":50}
  Response: {"id":"8","type":"ok"}

  Request:  {"id":"9","type":"ping"}
  Response: {"id":"9","type":"pong","version":"0.1.0"}

Usage (from Rust):
    Command::new("python")
        .args(["-m", "nala_orchestrator.cli", "--root", "/path/to/project"])
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::piped()).stdout(Stdio::piped()).spawn()?;
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from .config import Config
from .agents.orchestrator import AgentOrchestrator
from .perspectives.engine import PerspectivesEngine, format_results_as_text
from .sessions.manager import SessionManager

# Flush immediately — Rust reads line-by-line
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

VERSION = "0.1.0"


def write_response(data: dict) -> None:
    """Write a JSON-lines response to stdout."""
    print(json.dumps(data), flush=True)


def _stream_text(req_id: str, text: str, chunk_size: int = 200) -> None:
    """Stream a long text string as successive chunk messages, then done."""
    for i in range(0, len(text), chunk_size):
        write_response({"id": req_id, "type": "chunk", "text": text[i:i + chunk_size]})
    write_response({"id": req_id, "type": "done"})


# ── Request handlers ───────────────────────────────────────────────────────

async def handle_request(
    req: dict,
    agent: AgentOrchestrator,
    root: Path,
    config: Config,
) -> None:
    """Dispatch one request and write response(s) to stdout."""
    req_id = req.get("id", "0")
    req_type = req.get("type", "")

    # ── Ping ──────────────────────────────────────────────────────────────
    if req_type == "ping":
        write_response({"id": req_id, "type": "pong", "version": VERSION})

    # ── Index context update ───────────────────────────────────────────────
    elif req_type == "index_context":
        agent.update_index_context(
            total_files=req.get("total_files", 0),
            total_symbols=req.get("total_symbols", 0),
        )
        write_response({"id": req_id, "type": "ok"})

    # ── Natural language query (streaming) ────────────────────────────────
    elif req_type == "query":
        text = req.get("text", "").strip()
        if not text:
            write_response({"id": req_id, "type": "error", "text": "Empty query"})
            return
        try:
            async for chunk in agent.stream_query(text):
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Run perspectives (streaming formatted report) ─────────────────────
    elif req_type == "run_perspectives":
        project_root_str = req.get("project_root") or str(root)
        perspective_name = req.get("perspective", "all")
        try:
            engine = PerspectivesEngine(config)
            if perspective_name == "all":
                results = await engine.run_all(project_root_str)
            else:
                result = await engine.run_one(perspective_name, project_root_str)
                results = [result] if result else []

            # Save findings to active session
            session = agent.ensure_session()
            session.save_findings(results)

            _stream_text(req_id, format_results_as_text(results))
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": f"Analysis error: {e}"})

    # ── Generate mission document (streaming) ─────────────────────────────
    elif req_type == "generate_mission":
        focus = req.get("focus", "").strip()
        try:
            session = agent.ensure_session()
            findings_raw = session.load_findings_raw()

            # Build the prompt from saved findings
            prompt = _build_mission_prompt(findings_raw, focus, agent)

            full_text: list[str] = []
            async for chunk in agent.stream_query(prompt):
                write_response({"id": req_id, "type": "chunk", "text": chunk})
                full_text.append(chunk)
            write_response({"id": req_id, "type": "done"})

            # Save the generated mission to the session
            if full_text:
                mission_md = "".join(full_text)
                existing = list(session.current_dir.glob("missions/MISSION_*.md")) if session.current_dir else []
                n = len(existing) + 1
                session.write_mission(n, mission_md)
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": f"Generation error: {e}"})

    # ── Session: list ──────────────────────────────────────────────────────
    elif req_type == "list_sessions":
        try:
            sm = SessionManager(root)
            sessions = sm.list_sessions()
            session_list = [
                {
                    "session_id": s.session_id,
                    "created_at": s.created_at,
                    "project_name": s.project_name,
                    "status": s.status,
                    "total_turns": s.total_turns,
                    "perspectives_run": s.perspectives_run,
                }
                for s in sessions[:20]
            ]
            write_response({"id": req_id, "type": "sessions", "sessions": session_list})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Session: new ──────────────────────────────────────────────────────
    elif req_type == "new_session":
        try:
            sm = SessionManager(root)
            meta = sm.new_session()
            agent.set_session(sm)
            # Clear in-memory conversation history for the fresh session
            agent.context.messages.clear()
            write_response({
                "id": req_id,
                "type": "session_created",
                "session_id": meta.session_id,
                "summary": f"New session {meta.session_id} created.",
            })
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Session: load ─────────────────────────────────────────────────────
    elif req_type == "load_session":
        session_id = req.get("session_id", "")
        if not session_id:
            write_response({"id": req_id, "type": "error", "text": "Missing session_id"})
            return
        try:
            sm = SessionManager(root)
            meta = sm.load_session(session_id)
            if meta is None:
                write_response({"id": req_id, "type": "error", "text": f"Session {session_id!r} not found"})
                return
            agent.context.messages.clear()
            agent.restore_history(sm)
            turns = sm.get_conversation_history()
            write_response({
                "id": req_id,
                "type": "session_loaded",
                "session_id": session_id,
                "turn_count": len(turns),
                "summary": sm.summary_text(),
            })
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Session: summary ──────────────────────────────────────────────────
    elif req_type == "session_summary":
        session = agent._session
        if session:
            text = session.summary_text()
        else:
            text = "No active session. Run a query or /analyze to start one."
        write_response({"id": req_id, "type": "session_summary", "text": text})

    else:
        write_response({"id": req_id, "type": "error", "text": f"Unknown type: {req_type}"})


# ── Mission prompt builder ─────────────────────────────────────────────────

def _build_mission_prompt(
    findings_raw: list[dict],
    focus: str,
    agent: AgentOrchestrator,
) -> str:
    """Build the LLM prompt for mission generation from saved findings."""
    project_name = Path(agent.context.project_root).name

    # Summarise findings
    finding_lines: list[str] = []
    for perspective_data in findings_raw:
        p_name = perspective_data.get("perspective_name", "unknown")
        findings = perspective_data.get("findings", [])
        if not findings:
            continue
        finding_lines.append(f"\n### {p_name} ({len(findings)} findings)")
        severity_order = ["critical", "high", "medium", "low", "info"]
        sorted_findings = sorted(
            findings,
            key=lambda f: severity_order.index(f.get("severity", "info"))
            if f.get("severity") in severity_order else 99
        )
        for f in sorted_findings[:5]:
            sev = f.get("severity", "?").upper()
            title = f.get("title", "Untitled")
            fp = f.get("file_path", "")
            line = f.get("start_line", 0)
            loc = f" ({fp}:{line})" if fp else ""
            finding_lines.append(f"- [{sev}] {title}{loc}")

    findings_section = "\n".join(finding_lines) or "No findings recorded."
    focus_line = f"\nFocus specifically on: {focus}" if focus else ""

    return f"""You are a senior software engineer performing a code review of **{project_name}**.
You have just completed an automated analysis. Generate a detailed, actionable improvement mission.

## Findings Summary
{findings_section}

## Project Context
Location: {agent.context.project_root}
Files: {agent.context.total_files} | Symbols: {agent.context.total_symbols}
{focus_line}

Generate a mission document in EXACTLY this format:

# Mission: [descriptive title]

## Objective
[1–2 sentences: what will be fixed and why]

## Why This Matters
[2–3 sentences: business/engineering impact]

## Implementation Steps
[Numbered list with enough detail to act on. Reference actual file names and line numbers.]

## Acceptance Criteria
- [ ] [verifiable outcome]
- [ ] [verifiable outcome]

## Estimated Complexity
[Low / Medium / High with 1-sentence justification]

Rules:
- Reference actual file names from the findings (not generic placeholders)
- Each step must be specific enough to implement without guessing
- Do not invent findings not present in the analysis above
"""


# ── IPC loop ───────────────────────────────────────────────────────────────

async def run_ipc_loop(project_root: Optional[str] = None) -> None:
    """
    Main IPC loop: read JSON-lines from stdin, write responses to stdout.
    Runs until stdin closes (Rust process exits or sends EOF).
    """
    root = Path(project_root) if project_root else Path.cwd()
    config = Config.load(project_root=root)
    agent = AgentOrchestrator(config)

    # Auto-create a session on startup so the first query is always logged
    sm = SessionManager(root)
    sm.new_session()
    agent.set_session(sm)

    # Signal ready
    write_response({
        "type": "ready",
        "has_llm": config.has_llm(),
        "provider": config.llm_provider,
        "version": VERSION,
    })

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            line = await reader.readline()
            if not line:
                break  # EOF — Rust side closed stdin
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            req = json.loads(line)
            # Concurrent dispatch — streaming doesn't block pings
            asyncio.create_task(handle_request(req, agent, root, config))
        except json.JSONDecodeError as e:
            write_response({"type": "error", "text": f"JSON parse error: {e}"})
        except Exception as e:
            write_response({"type": "error", "text": f"IPC error: {e}"})
            break

    # Graceful shutdown — mark session complete
    if agent._session:
        agent._session.complete()


def main() -> None:
    """Entry point: parse optional --root arg and run the IPC loop."""
    import argparse
    parser = argparse.ArgumentParser(description="Nala Python IPC server")
    parser.add_argument("--root", default=None, help="Project root directory")
    args = parser.parse_args()
    asyncio.run(run_ipc_loop(args.root))


if __name__ == "__main__":
    main()
