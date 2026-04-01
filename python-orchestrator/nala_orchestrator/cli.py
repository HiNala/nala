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
  ── Inline actions ────────────────────────────────────────────────────────
  Request:  {"id":"A","type":"query_with_actions","text":"..."}
  Response: (chunk/done like query, then…)
            {"id":"A","type":"proposed_action","action_id":"abc","action_type":"edit","description":"…","preview":"…"}

  Request:  {"id":"B","type":"apply_action","action_id":"abc"}
  Response: {"id":"B","type":"action_applied","action_id":"abc","success":true,"message":"Edited src/foo.py"}

  Request:  {"id":"C","type":"skip_action","action_id":"abc"}
  Response: {"id":"C","type":"ok"}

  ── Multi-agent team ──────────────────────────────────────────────────────
  Request:  {"id":"T","type":"team_start","objective":"..."}
  Response: (chunk/done streaming progress + final summary)

  Request:  {"id":"T","type":"team_status"}
  Response: (chunk/done with task list + lock status)

  Request:  {"id":"T","type":"team_cancel"}
  Response: {"id":"T","type":"ok","text":"Team cancelled."}

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
from .agents.action_extractor import extract_actions
from .agents.action_executor import ActionExecutor
from .perspectives.engine import PerspectivesEngine, format_results_as_text
from .sessions.manager import SessionManager
from .chunking.splitter import ChunkSplitter, Symbol
from .chunking.embedder import Embedder
from .memory.session_memory import SessionMemory
from .memory.knowledge import KnowledgeBase
from .handoff.writer import HandoffWriter
from .handoff.reader import HandoffReader
from .multi_agent.lead import LeadAgent

# Per-process store of proposed actions keyed by action_id.
# Cleared when a new session starts.
_pending_actions: dict[str, object] = {}

# Project-level embedder (built lazily on first index_context with symbols).
_embedder: Optional[Embedder] = None

# Singleton lead agent — created on first team_start, reused for status/cancel.
_lead_agent: Optional[LeadAgent] = None

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
        total_files = req.get("total_files", 0)
        total_symbols = req.get("total_symbols", 0)
        agent.update_index_context(total_files=total_files, total_symbols=total_symbols)

        # Rebuild chunk index if stale.
        global _embedder
        symbols_raw: list[dict] = req.get("symbols", [])
        if symbols_raw:
            syms = [
                Symbol(
                    name=s.get("name", ""),
                    kind=s.get("kind", ""),
                    start_line=s.get("start_line", 1),
                    end_line=s.get("end_line", 1),
                    file_path=s.get("file_path", ""),
                )
                for s in symbols_raw
            ]
            if _embedder is None or _embedder.needs_rebuild(total_files):
                _embedder = Embedder(str(root))
                splitter = ChunkSplitter()
                chunks = splitter.split_all(str(root), syms)
                _embedder.build(chunks)
                agent.set_embedder(_embedder)

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
            # Clear in-memory conversation history and pending actions
            agent.context.messages.clear()
            _pending_actions.clear()
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

    # ── Query with inline actions (streaming + action extraction) ─────────
    elif req_type == "query_with_actions":
        text = req.get("text", "").strip()
        if not text:
            write_response({"id": req_id, "type": "error", "text": "Empty query"})
            return
        try:
            full_text: list[str] = []
            async for chunk in agent.stream_query_with_actions(text):
                write_response({"id": req_id, "type": "chunk", "text": chunk})
                full_text.append(chunk)
            write_response({"id": req_id, "type": "done"})

            # Extract and register proposed actions
            if full_text:
                assembled = "".join(full_text)
                _cleaned, actions = extract_actions(assembled)
                for action in actions:
                    _pending_actions[action.action_id] = action
                    executor = ActionExecutor(root)
                    preview = executor.preview(action)
                    write_response({
                        "id": req_id,
                        "type": "proposed_action",
                        "action_id": action.action_id,
                        "action_type": action.type,
                        "description": action.description,  # type: ignore[attr-defined]
                        "preview": preview,
                    })
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Apply a proposed action ────────────────────────────────────────────
    elif req_type == "apply_action":
        action_id = req.get("action_id", "")
        action = _pending_actions.get(action_id)
        if action is None:
            write_response({"id": req_id, "type": "error", "text": f"Unknown action_id: {action_id}"})
            return
        try:
            executor = ActionExecutor(root)
            result = executor.apply(action)  # type: ignore[arg-type]
            # Persist to session audit log
            session = agent.ensure_session()
            session.append_turn(
                "action",
                json.dumps({
                    "action_id": result.action_id,
                    "success": result.success,
                    "message": result.message,
                }),
            )
            write_response({
                "id": req_id,
                "type": "action_applied",
                "action_id": result.action_id,
                "success": result.success,
                "message": result.message,
                "output": result.output,
            })
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Skip a proposed action (acknowledge, no file changes) ─────────────
    elif req_type == "skip_action":
        action_id = req.get("action_id", "")
        _pending_actions.pop(action_id, None)
        write_response({"id": req_id, "type": "ok"})

    # ── Handoff: manual save ──────────────────────────────────────────────
    elif req_type == "handoff_save":
        try:
            history = [{"role": m.role, "content": m.content}
                       for m in agent.context.messages]
            sid = (agent._session.current_meta.session_id
                   if agent._session and agent._session.current_meta else "manual")
            writer = HandoffWriter(root)
            doc = writer.write(sid, "manual", history)
            _stream_text(req_id, f"Handoff saved.\n\n{doc.to_markdown()}")
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Handoff: show latest ───────────────────────────────────────────────
    elif req_type == "handoff_show":
        reader = HandoffReader(root)
        doc = reader.load_latest()
        if doc:
            _stream_text(req_id, doc.to_markdown())
        else:
            _stream_text(req_id, "No handoff document found.")

    # ── Handoff: history chain ─────────────────────────────────────────────
    elif req_type == "handoff_history":
        reader = HandoffReader(root)
        _stream_text(req_id, reader.format_history())

    # ── Memory: project knowledge summary ────────────────────────────────
    elif req_type == "memory_summary":
        kb = KnowledgeBase(root)
        sm_mem = SessionMemory(root)
        kb_text = kb.get_summary()
        recent = sm_mem.list_sessions(5)
        sessions_text = "\n".join(
            f"  {s['session_id']}: {s['summary']}" for s in recent
        ) or "  (no sessions yet)"
        text = f"{kb_text}\n\nRecent sessions:\n{sessions_text}"
        _stream_text(req_id, text)

    # ── Memory: list sessions ─────────────────────────────────────────────
    elif req_type == "memory_sessions":
        sm_mem = SessionMemory(root)
        sessions = sm_mem.list_sessions(30)
        write_response({"id": req_id, "type": "memory_sessions", "sessions": sessions})

    # ── Memory: forget a topic ─────────────────────────────────────────────
    elif req_type == "memory_forget":
        topic = req.get("topic", "").strip()
        if not topic:
            write_response({"id": req_id, "type": "error", "text": "Missing topic"})
        else:
            kb = KnowledgeBase(root)
            count = kb.remove_fact(topic)
            write_response({"id": req_id, "type": "ok",
                            "text": f"Removed {count} fact(s) matching '{topic}'"})

    # ── Context: usage breakdown ──────────────────────────────────────────
    elif req_type == "context_usage":
        breakdown = agent.get_context_breakdown_text()
        _stream_text(req_id, breakdown)

    # ── Context: manual compaction (writes handoff first) ────────────────
    elif req_type == "compact_context":
        focus = req.get("focus", "").strip()
        # Write a handoff before compacting so context is never lost.
        try:
            history = [{"role": m.role, "content": m.content}
                       for m in agent.context.messages]
            sid = (agent._session.current_meta.session_id
                   if agent._session and agent._session.current_meta else "compact")
            HandoffWriter(root).write(sid, "compaction", history)
        except Exception:
            pass
        summary_msg = agent.compact_now(focus=focus)
        _stream_text(req_id, f"Compaction complete.\n{summary_msg}")

    # ── Session: summary ──────────────────────────────────────────────────
    elif req_type == "session_summary":
        session = agent._session
        if session:
            text = session.summary_text()
        else:
            text = "No active session. Run a query or /analyze to start one."
        write_response({"id": req_id, "type": "session_summary", "text": text})

    # ── Multi-agent: start a team run (streaming progress) ───────────────
    elif req_type == "team_start":
        objective = req.get("objective", "").strip()
        if not objective:
            write_response({"id": req_id, "type": "error", "text": "Missing objective"})
            return
        global _lead_agent
        _lead_agent = LeadAgent(config, root)
        try:
            async for chunk in _lead_agent.stream_run(objective):
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": f"Team run error: {e}"})

    # ── Multi-agent: status of running/last team ──────────────────────────
    elif req_type == "team_status":
        if _lead_agent is None:
            _stream_text(req_id, "No team run active.")
        else:
            _stream_text(req_id, _lead_agent.get_status())

    # ── Multi-agent: cancel / reset ───────────────────────────────────────
    elif req_type == "team_cancel":
        if _lead_agent is not None:
            _lead_agent._task_list.clear()
            _lead_agent._bus.clear()
        _lead_agent = None
        write_response({"id": req_id, "type": "ok", "text": "Team cancelled."})

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

    # Initialise the embedder (BM25 works offline; vector index is lazy).
    global _embedder
    _embedder = Embedder(str(root))
    agent.set_embedder(_embedder)

    # Inject handoff + memory context so the agent resumes seamlessly.
    handoff_reader = HandoffReader(root)
    session_mem = SessionMemory(root)
    knowledge_base = KnowledgeBase(root)

    handoff_ctx = handoff_reader.get_startup_injection()
    session_ctx = session_mem.get_startup_injection()
    kb_ctx = knowledge_base.load_for_context(max_chars=2000)

    if handoff_ctx:
        agent.context.inject_system(handoff_ctx)
    elif session_ctx:
        agent.context.inject_system(session_ctx)
    if kb_ctx:
        agent.context.inject_system(f"[PROJECT KNOWLEDGE]\n{kb_ctx}\n[END KNOWLEDGE]")

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

    # Graceful shutdown — write handoff, save memory, mark session complete.
    if agent._session:
        try:
            history = [{"role": m.role, "content": m.content}
                       for m in agent.context.messages]
            sid = (agent._session.current_meta.session_id
                   if agent._session.current_meta else "unknown")
            if history:
                # Write handoff document for continuity
                writer = HandoffWriter(root)
                writer.write(sid, "session_end", history)
                # Save session memory and extract knowledge
                session_mem = SessionMemory(root)
                record = session_mem.build_and_save(sid, history)
                knowledge_base = KnowledgeBase(root)
                knowledge_base.extract_from_session(record.to_markdown())
        except Exception:
            pass  # Never crash on shutdown
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
